"""并行预算传导（config.timeout / read_timeout）单元测试。"""

import time
from unittest.mock import Mock, patch

import pytest

from aw.base_aw import BaseAW, AWError
from common.parallel import set_deadline
from common.testagent_client import TestagentClient


class BudgetAW(BaseAW):
    """预算传导演示 AW。"""

    PLATFORM = "web"

    def do_click(self):
        """点击操作。"""
        self.ocr_click("登录")


def make_user():
    user = Mock()
    user.user_id = "userA"
    user.platform = "web"
    user.account = "acc"
    user.password = "pwd"
    user.name = "Name"
    user.ip = "127.0.0.1"
    user.device_id = ""
    return user


def ok_result():
    return {"actions": [{"status": "success"}]}


def test_budget_passed_as_config_and_read_timeout():
    """并行执行时请求带剩余预算 config，且 read_timeout 覆盖剩余预算。"""
    client = Mock()
    client.execute.return_value = ok_result()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() + 60)  # 剩余 60s > 125s 缓冲下限? 60+15=75 < 125
        aw.ocr_click("登录")
    finally:
        set_deadline(None)

    _, kwargs = client.execute.call_args
    assert 55000 <= kwargs["config"]["timeout"] <= 60000  # 剩余毫秒
    assert kwargs["timeout"] == 125.0  # max(125, 60+15)


def test_budget_extends_read_timeout_over_default():
    """剩余预算超过默认 read_timeout 时按预算放大。"""
    client = Mock()
    client.execute.return_value = ok_result()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() + 200)  # 200+15=215 > 125
        aw.ocr_click("登录")
    finally:
        set_deadline(None)

    _, kwargs = client.execute.call_args
    assert 190000 <= kwargs["config"]["timeout"] <= 200000
    assert 125.0 < kwargs["timeout"] <= 215.0


def test_no_budget_outside_parallel():
    """非并行执行不带 config 与 timeout（现状行为）。"""
    client = Mock()
    client.execute.return_value = ok_result()
    aw = BudgetAW(client, make_user())

    aw.ocr_click("登录")

    _, kwargs = client.execute.call_args
    assert kwargs["config"] is None
    assert kwargs["timeout"] is None


def test_exhausted_budget_raises_before_request():
    """预算已耗尽时不发请求，直接抛 AWError。"""
    client = Mock()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() - 1)  # 已过期
        with pytest.raises(AWError, match="预算已耗尽"):
            aw.ocr_click("登录")
    finally:
        set_deadline(None)

    assert client.execute.call_count == 0


def test_client_request_per_request_timeout():
    """TestagentClient._request 支持单请求覆盖 read_timeout。"""
    client = TestagentClient("http://127.0.0.1:9", connect_timeout=5, read_timeout=10)

    with patch.object(client.session, "request") as request:
        request.side_effect = Exception("stop here")
        with pytest.raises(Exception):
            client._request("POST", "/task/execute", data={}, timeout=42.0)

    _, kwargs = request.call_args
    assert kwargs["timeout"] == (5, 42.0)


def test_budget_exhausted_business_method_skips_screenshot():
    """业务方法中途预算耗尽时，装饰器不再补拍截图（不发任何请求）。"""
    client = Mock()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() - 1)  # 预算已耗尽
        with pytest.raises(AWError, match="预算已耗尽"):
            aw.do_click()
    finally:
        set_deadline(None)

    # 原子层不发请求 + 装饰器不补拍截图
    assert client.execute.call_count == 0
