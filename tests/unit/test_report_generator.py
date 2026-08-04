"""HTML 报告增强功能测试。"""

from types import SimpleNamespace

from aw.base_aw import BaseAW
from common.report_generator import HTMLReportGenerator
from common.report_logger import ReportLogger


class DemoAW(BaseAW):
    """用于验证 AW 自定义日志的测试 AW。"""

    PLATFORM = "windows"

    def do_demo(self):
        """执行演示操作。"""
        self.log("XXXX")


def _user(user_id="userA", platform="windows"):
    """构造最小用户对象。"""
    return SimpleNamespace(
        user_id=user_id,
        platform=platform,
        account="account",
        password="password",
        name="测试用户",
        ip="127.0.0.1",
        _get_ui_platform=lambda: "windows",
    )


def test_aw_log_is_grouped_into_current_business_step():
    """AW 内日志应归入当前业务步骤。"""
    ReportLogger.reset()
    DemoAW(None, _user()).do_demo()

    logs = ReportLogger.get_current().get_logs()
    aw_logs = [log for log in logs if log.get("type") == "aw_log"]
    assert len(aw_logs) == 1
    assert aw_logs[0]["message"] == "XXXX"
    assert aw_logs[0]["parent_call_id"]

    timeline = HTMLReportGenerator._build_timeline(logs)
    group = next(item for item in timeline if item["kind"] == "group")
    assert any(row.get("type") == "aw_log" for row in group["rows"])


def test_report_displays_user_device_types_for_multiple_users():
    """多用户报告应使用可换行的资源卡片展示设备类型。"""
    logs = [
        {
            "time": "10:00:00.000",
            "type": "aw_call",
            "aw_name": "DemoAW",
            "method": "ocr_wait",
            "args": {"user_id": "userA", "user_name": "张三", "user_ip": "127.0.0.1"},
            "success": True,
            "result": {"status": "success"},
            "duration_ms": 10,
            "parent_call_id": "call-1",
            "parent_aw": "DemoAW.do_demo",
            "parent_display": "执行演示操作",
        }
    ]
    details = {
        f"user{chr(65 + index)}": {
            "name": f"用户{index + 1}",
            "ip": f"127.0.0.{index + 1}",
            "display_platform": platform,
        }
        for index, platform in enumerate([
            "windows", "ios", "android", "web", "mac", "harmony_pc", "harmony_mobile"
        ])
    }
    report_path = SimpleNamespace(html="")
    report_path.write_text = lambda content, encoding="utf-8": setattr(report_path, "html", content)
    HTMLReportGenerator.generate(report_path, "test_multi_user", logs=logs, user_details=details)
    html = report_path.html

    assert "resource-grid" in html
    assert "userA" in html and "userG" in html
    assert "Windows" in html and "iOS" in html and "Android" in html
    assert "Web" in html and "macOS" in html
    assert "Harmony PC" in html and "Harmony Mobile" in html


def test_api_user_does_not_inherit_ui_device_type():
    """API 用户标签不应显示关联 UI 用户的设备类型。"""
    group = {
        "ok": True,
        "rows": [],
        "children": [],
        "user_id": "userA_api",
        "user_platform": "web",
        "title": "创建会议",
        "method_label": "MeetingManageAW.do_create_meeting",
        "duration_ms": 10,
        "total_rows": 0,
        "fail_total": 0,
        "fail_rows": 0,
    }
    html = HTMLReportGenerator._render_group(
        group,
        "g1",
        user_details={
            "userA_api": {
                "is_api": True,
                "display_platform": "web",
            }
        },
    )

    assert "userA_api" in html
    assert "API/Web" not in html
    assert "userA_api · Web" not in html


def test_http_row_displays_status_and_response_body():
    """HTTP AW 日志应同时展示请求和响应。"""
    log = {
        "time": "10:00:00.000",
        "type": "aw_call",
        "aw_name": "MeetingManageAW",
        "method": "POST",
        "args": {
            "user_id": "userA_api",
            "url": "https://example.test/meetings",
            "method": "POST",
            "body": {"subject": "演示会议"},
        },
        "success": True,
        "result": {"status_code": 200, "body": '{"meetingId":"m-001","status":"created"}'},
        "duration_ms": 20,
    }
    html = HTMLReportGenerator._render_row_detail(log)

    assert "HTTP 请求" in html
    assert "HTTP 响应" in html
    assert "状态码 200" in html
    assert "meetingId" in html and "m-001" in html
