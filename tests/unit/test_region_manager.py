"""RegionManager 畸形 YAML 处理测试。

背景：反馈称 region 区域 YAML 格式有问题（如 [1,2,3,4 ]）时，
要么静默失败要么异常类型不明显。要求：
1. 合法变体（] 前有空格、尾逗号）正常加载；
2. YAML 解析失败 / 顶层非 dict / 条目非法时，写 warning 到报告日志
   （ReportLogger），不允许静默吞掉；
3. 区域名查不到时抛出带明确指引的异常，而不是返回 None 静默丢弃 region。
"""

import pytest

from aw.base_aw import BaseAW
from common.region_manager import RegionManager
from common.report_logger import ReportLogger


class FakeUser:
    """最小 user 替身，提供 _resolve_region 与 self.log() 需要的字段。"""

    platform = "web"
    user_id = "u-1"
    account = "acc-1"
    name = "tester"
    ip = "127.0.0.1"


def _make_aw() -> BaseAW:
    """构造一个仅用于参数解析测试的 BaseAW（client 不参与解析）。"""
    return BaseAW(client=None, user=FakeUser())


def _warning_messages() -> list:
    """取当前线程报告日志中的 warning 文本列表。"""
    logs = ReportLogger.get_current().get_logs()
    return [
        entry["message"]
        for entry in logs
        if entry.get("type") == "aw_log" and entry.get("level") == "warning"
    ]


def _load(tmp_path, content: str) -> None:
    """把内容写到临时 web.yaml 并用真实加载逻辑载入。"""
    filepath = tmp_path / "web.yaml"
    filepath.write_text(content, encoding="utf-8")
    RegionManager.reload()
    RegionManager.get_instance()._load_platform("web", str(filepath))


def test_trailing_space_and_comma_are_valid_yaml(tmp_path):
    """反馈例子 [1,2,3,4 ]：] 前空格和尾逗号都是合法 YAML，应正常加载。"""
    _load(tmp_path, "ok_region: [1,2,3,4 ]\ncomma_region: [1,2,3,4,]\n")

    assert RegionManager.get_instance().get_region("web", "ok_region") == [1, 2, 3, 4]
    assert RegionManager.get_instance().get_region("web", "comma_region") == [1, 2, 3, 4]


def test_yaml_parse_error_warns_to_report(tmp_path):
    """缺右括号导致 YAML 解析失败时，应写 warning 到报告日志而非静默吞掉。"""
    ReportLogger.reset()
    _load(tmp_path, "ok_region: [1,2,3,4\n")

    assert RegionManager.get_instance().get_region("web", "ok_region") is None
    warnings = _warning_messages()
    assert any("web.yaml" in message for message in warnings), (
        f"应有包含配置文件名的 warning，实际: {warnings}"
    )


def test_top_level_non_dict_yaml_does_not_crash(tmp_path):
    """顶层不是映射（如整个文件是列表）时不应抛 AttributeError。"""
    ReportLogger.reset()
    _load(tmp_path, "[1,2,3,4 ]\n")

    assert RegionManager._configs.get("web") == {}
    assert _warning_messages(), "顶层非 dict 应产生 warning 日志"


def test_invalid_entries_warn_with_reason(tmp_path):
    """非法条目（长度/类型不符）应逐条 warning 并保留合法兄弟条目。"""
    ReportLogger.reset()
    _load(
        tmp_path,
        "good: [1,2,3,4]\n"
        "bad_len: [1,2,3]\n"
        "bad_float: [1.0,2,3,4]\n"
        "bad_str: ['1','2','3','4']\n",
    )

    region_manager = RegionManager.get_instance()
    assert region_manager.get_region("web", "good") == [1, 2, 3, 4]
    assert region_manager.get_region("web", "bad_len") is None
    assert region_manager.get_region("web", "bad_float") is None
    assert region_manager.get_region("web", "bad_str") is None

    warnings = "\n".join(_warning_messages())
    for name in ("bad_len", "bad_float", "bad_str"):
        assert name in warnings, f"warning 中应提到非法条目 {name}，实际: {warnings}"


def test_resolve_region_unknown_name_raises_clear_error(tmp_path):
    """字符串区域名查不到时应抛带指引的异常，而非静默返回 None。"""
    _load(tmp_path, "good: [1,2,3,4]\n")

    with pytest.raises(ValueError) as exc_info:
        _make_aw()._resolve_region("not_exist")

    message = str(exc_info.value)
    assert "not_exist" in message
    assert "web" in message
    assert "good" in message, "报错应列出可用区域名"
    assert "config/regions" in message, "报错应指出配置文件位置"


def test_resolve_region_none_and_list_passthrough(tmp_path):
    """None 和坐标 list 应保持原语义：None → None，list 原样返回。"""
    assert _make_aw()._resolve_region(None) is None
    assert _make_aw()._resolve_region([0, 0, 10, 10]) == [0, 0, 10, 10]
