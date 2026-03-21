"""HTMLReportGenerator 测试。"""

import pytest
from pathlib import Path
import tempfile
from common.report_generator import HTMLReportGenerator


class TestHTMLReportGenerator:
    """HTMLReportGenerator 测试类。"""

    def test_generate_creates_file(self):
        """测试生成文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_case.html"

            HTMLReportGenerator.generate(
                report_path=report_path,
                case_name="test_login_success",
                case_title="登录成功测试",
                logs=[],
                duration_ms=1000,
                status="passed"
            )

            assert report_path.exists()

    def test_generate_contains_case_name(self):
        """测试报告包含用例名称。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_case.html"

            HTMLReportGenerator.generate(
                report_path=report_path,
                case_name="test_login_success",
                case_title="登录成功测试",
                logs=[],
                duration_ms=1000,
                status="passed"
            )

            content = report_path.read_text(encoding="utf-8")
            assert "test_login_success" in content
            assert "登录成功测试" in content

    def test_generate_contains_failed_steps(self):
        """测试报告包含失败步骤。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_case.html"

            logs = [
                {"type": "aw_call", "aw_name": "LoginAW", "method": "do_login",
                 "success": False, "result": {"error": "timeout"}, "duration_ms": 100,
                 "time": "10:00:00.000"}
            ]

            HTMLReportGenerator.generate(
                report_path=report_path,
                case_name="test_case",
                logs=logs,
                duration_ms=1000,
                status="failed"
            )

            content = report_path.read_text(encoding="utf-8")
            assert "失败步骤" in content
            assert "LoginAW.do_login" in content

    def test_generate_contains_screenshot(self):
        """测试报告包含截图。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_case.html"

            logs = [
                {"type": "screenshot", "user_id": "userA", "base64": "dGVzdA==", "time": "10:00:00.000"}
            ]

            HTMLReportGenerator.generate(
                report_path=report_path,
                case_name="test_case",
                logs=logs,
                duration_ms=1000,
                status="failed"
            )

            content = report_path.read_text(encoding="utf-8")
            assert "data:image/png;base64" in content
            assert "userA" in content

    def test_generate_passed_status_green(self):
        """测试通过状态显示绿色。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_case.html"

            HTMLReportGenerator.generate(
                report_path=report_path,
                case_name="test_case",
                logs=[],
                duration_ms=1000,
                status="passed"
            )

            content = report_path.read_text(encoding="utf-8")
            assert "status-passed" in content
            assert "通过" in content

    def test_generate_failed_status_red(self):
        """测试失败状态显示红色。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_case.html"

            HTMLReportGenerator.generate(
                report_path=report_path,
                case_name="test_case",
                logs=[],
                duration_ms=1000,
                status="failed"
            )

            content = report_path.read_text(encoding="utf-8")
            assert "status-failed" in content
            assert "失败" in content