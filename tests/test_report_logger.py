"""ReportLogger 测试。"""

import threading
import pytest
import time
from common.report_logger import ReportLogger


class TestReportLogger:
    """ReportLogger 测试类。"""

    def test_log_step(self):
        """测试记录步骤。"""
        logger = ReportLogger()
        logger.log_step("用例开始", "初始化完成")

        logs = logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["type"] == "step"
        assert logs[0]["step"] == "用例开始"
        assert logs[0]["detail"] == "初始化完成"

    def test_log_aw_call(self):
        """测试记录 AW 调用。"""
        logger = ReportLogger()
        logger.log_aw_call(
            aw_name="LoginAW",
            method="do_login",
            args={"username": "test"},
            success=True,
            result={},
            duration_ms=100
        )

        logs = logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["type"] == "aw_call"
        assert logs[0]["aw_name"] == "LoginAW"
        assert logs[0]["method"] == "do_login"
        assert logs[0]["success"] is True
        assert logs[0]["duration_ms"] == 100

    def test_log_worker_call(self):
        """测试记录 Worker 调用。"""
        logger = ReportLogger()
        logger.log_worker_call(
            api="ocr_click",
            params={"text": "登录"},
            success=True,
            response={"success": True},
            duration_ms=50
        )

        logs = logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["type"] == "worker_call"
        assert logs[0]["api"] == "ocr_click"
        assert logs[0]["success"] is True

    def test_log_screenshot(self):
        """测试记录截图。"""
        logger = ReportLogger()
        logger.log_screenshot("userA", "base64data123")

        logs = logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["type"] == "screenshot"
        assert logs[0]["user_id"] == "userA"
        assert logs[0]["base64"] == "base64data123"

    def test_log_error(self):
        """测试记录错误。"""
        logger = ReportLogger()
        logger.log_error("操作失败")

        logs = logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["type"] == "error"
        assert logs[0]["error"] == "操作失败"

    def test_get_duration(self):
        """测试获取执行时长。"""
        logger = ReportLogger()
        time.sleep(0.1)
        duration = logger.get_duration()

        assert duration >= 100

    def test_reset_clears_logs(self):
        """测试重置清空日志。"""
        logger = ReportLogger()
        logger.log_step("测试")
        ReportLogger.reset()

        new_logger = ReportLogger.get_current()
        assert len(new_logger.get_logs()) == 0

    def test_thread_safety(self):
        """测试线程安全。"""
        logger = ReportLogger()
        threads = []

        def add_logs():
            for i in range(100):
                logger.log_step(f"step_{threading.current_thread().name}_{i}")

        for i in range(5):
            t = threading.Thread(target=add_logs, name=f"thread_{i}")
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 5 个线程各 100 条 = 500 条
        assert len(logger.get_logs()) == 500