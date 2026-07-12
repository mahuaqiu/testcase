"""测试用例公共契约静态测试。"""

import inspect
from pathlib import Path

from common.parallel import parallel
from common.testagent_client import TestagentClient as Client
from common.user import User
from aw.base_aw import BaseAW


ROOT = Path(__file__).parents[2]


def test_real_testcases_are_not_modified_by_this_change():
    changed = set()
    import subprocess

    output = subprocess.check_output(
        ["git", "diff", "--name-only", "--", "testcases"],
        cwd=ROOT,
        text=True,
    )
    changed.update(line for line in output.splitlines() if line)
    assert not changed


def test_public_signatures_remain_compatible():
    assert list(inspect.signature(parallel).parameters) == ["max_workers", "timeout"]
    async_params = list(inspect.signature(Client.execute_async).parameters)
    assert async_params[-1] == "idempotency_key"
    assert hasattr(User, "__getattr__")
    for name in ["ocr_click", "ocr_input", "ocr_wait", "ocr_assert", "click", "wait"]:
        assert hasattr(BaseAW, name)


def test_api_docs_describe_new_worker_contract():
    for path in [ROOT / "api.yaml", Path(r"D:\code\autotest\api.yaml")]:
        text = path.read_text(encoding="utf-8")
        assert "Idempotency-Key" in text
        assert "interrupted" in text
        assert "可重复轮询" in text
        assert "/ws/screen/{platform}/{device_id}" in text
        assert "可信真实 IDR" in text
