"""HTML 报告增强功能测试。"""

from types import SimpleNamespace

from aw.base_aw import BaseAW
from common.report_generator import HTMLReportGenerator
from common.report_logger import ReportLogger
from common.parallel import Action, ParallelActionError, ParallelExecutionError
from conftest import _record_test_failure


class DemoAW(BaseAW):
    """用于验证 AW 自定义日志的测试 AW。"""

    PLATFORM = "windows"

    def do_demo(self):
        """执行演示操作。"""
        self.log("XXXX")


class FailingDemoAW(BaseAW):
    """用于验证 AW 失败归属的测试 AW。"""

    PLATFORM = "windows"

    def should_fail(self):
        """断言演示失败。"""
        assert False, "未找到目标文字"


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


def test_unused_api_user_not_shown_in_report_filters():
    """声明了 userA/userB，但只调用 userA_api 时，不应出现 userB_api。"""
    logs = [
        {
            "time": "10:00:00.000",
            "type": "aw_call",
            "aw_name": "MeetingManageAW",
            "method": "do_create_meeting",
            "args": {"user_id": "userA_api", "user_name": "甲"},
            "success": True,
            "result": {"status_code": 200, "body": "{}"},
            "duration_ms": 10,
            "is_business_method": True,
            "call_id": "api-1",
            "display_name": "创建会议",
        },
        {
            "time": "10:00:01.000",
            "type": "aw_call",
            "aw_name": "LoginAW",
            "method": "do_login",
            "args": {"user_id": "userA", "user_name": "甲", "user_platform": "web"},
            "success": True,
            "result": {"status": "success"},
            "duration_ms": 20,
            "is_business_method": True,
            "call_id": "ui-1",
            "display_name": "执行登录操作",
        },
        {
            "time": "10:00:02.000",
            "type": "aw_call",
            "aw_name": "LoginAW",
            "method": "do_login",
            "args": {"user_id": "userB", "user_name": "乙", "user_platform": "windows"},
            "success": True,
            "result": {"status": "success"},
            "duration_ms": 20,
            "is_business_method": True,
            "call_id": "ui-2",
            "display_name": "执行登录操作",
        },
    ]
    details = {
        "userA": {"name": "甲", "ip": "1.1.1.1", "platform": "web", "display_platform": "web"},
        "userB": {"name": "乙", "ip": "1.1.1.2", "platform": "windows", "display_platform": "windows"},
        "userA_api": {"name": "甲", "platform": "api", "is_api": True},
        "userB_api": {"name": "乙", "platform": "api", "is_api": True},  # 未调用
    }
    users = HTMLReportGenerator._collect_user_details(logs, details)
    assert "userA" in users
    assert "userB" in users
    assert "userA_api" in users
    assert "userB_api" not in users

    report_path = SimpleNamespace(html="")
    report_path.write_text = lambda content, encoding="utf-8": setattr(report_path, "html", content)
    HTMLReportGenerator.generate(report_path, "test_api_filter", logs=logs, user_details=details)
    html = report_path.html
    assert "filterUser(this,'userA_api')" in html
    assert "filterUser(this,'userB_api')" not in html


def test_error_entry_follows_failed_user_in_filter():
    """错误堆栈应带 user_id，切换用户时只显示报错用户的条目。"""
    error_log = {
        "time": "10:00:05.000",
        "type": "error",
        "error": "userA 断言失败: 未找到目标文字",
        "user_id": "userA",
    }
    html = HTMLReportGenerator._render_error(error_log)
    assert 'data-user="userA"' in html
    assert "userA" in html
    assert "未找到目标文字" in html

    logs = [
        {
            "time": "10:00:01.000",
            "type": "aw_call",
            "aw_name": "LoginAW",
            "method": "do_login",
            "args": {"user_id": "userA"},
            "success": False,
            "result": {"error": "失败"},
            "duration_ms": 10,
            "is_business_method": True,
            "call_id": "c1",
            "display_name": "执行登录操作",
        },
        {
            "time": "10:00:02.000",
            "type": "aw_call",
            "aw_name": "LoginAW",
            "method": "do_login",
            "args": {"user_id": "userB"},
            "success": True,
            "result": {"status": "success"},
            "duration_ms": 10,
            "is_business_method": True,
            "call_id": "c2",
            "display_name": "执行登录操作",
        },
        error_log,
    ]
    report_path = SimpleNamespace(html="")
    report_path.write_text = lambda content, encoding="utf-8": setattr(report_path, "html", content)
    HTMLReportGenerator.generate(
        report_path,
        "test_error_filter",
        logs=logs,
        status="failed",
        user_details={
            "userA": {"platform": "web", "display_platform": "web"},
            "userB": {"platform": "windows", "display_platform": "windows"},
        },
    )
    html = report_path.html
    # 错误条目可按用户过滤
    assert 'class="error-entry" data-user="userA"' in html
    assert "error-entry:not(.match-user)" in html
    assert "el.dataset.user === uid" in html


def test_parallel_failure_error_follows_correct_user():
    """并行失败时每个错误归属自己的用户，过滤时正确显示。"""
    ReportLogger.reset()
    logger = ReportLogger.get_current()
    action_a = Action(
        action_data={}, aw_name="LoginAW", method="do_login", log_args={},
        user_id="userA", user_name="甲", user_account="a", user_ip="1.1.1.1",
        platform="web", client=None,
    )
    action_b = Action(
        action_data={}, aw_name="LoginAW", method="do_login", log_args={},
        user_id="userB", user_name="乙", user_account="b", user_ip="1.1.1.2",
        platform="windows", client=None,
    )
    raised = ParallelExecutionError([
        ParallelActionError(action_a, AssertionError("userA 断言失败")),
        ParallelActionError(action_b, AssertionError("userB 断言失败")),
    ])
    failure_scope = _record_test_failure(
        logger, "包含全部用户的 pytest traceback", raised
    )
    error_logs = [log for log in logger.get_logs() if log.get("type") == "error"]

    assert [log.get("user_id") for log in error_logs] == ["userA", "userB"]
    assert all("包含全部用户" not in log["error"] for log in error_logs)
    assert failure_scope["suppress_error_box"] is True

    # 并行场景模拟：两个用户各失败一次，conftest 会为每个失败的 action
    # 各记录一条 error 日志（对应 ParallelExecutionError.errors 拆分逻辑）。
    logs = [
        {
            "time": "10:00:01.000",
            "type": "aw_call",
            "aw_name": "LoginAW",
            "method": "do_login",
            "args": {"user_id": "userA"},
            "success": False,
            "result": {"error": "userA 断言失败"},
            "duration_ms": 10,
            "is_business_method": True,
            "call_id": "c1",
            "display_name": "执行登录操作",
        },
        {
            "time": "10:00:02.000",
            "type": "aw_call",
            "aw_name": "LoginAW",
            "method": "do_login",
            "args": {"user_id": "userB"},
            "success": False,
            "result": {"error": "userB 断言失败"},
            "duration_ms": 10,
            "is_business_method": True,
            "call_id": "c2",
            "display_name": "执行登录操作",
        },
        *error_logs,
    ]
    report_path = SimpleNamespace(html="")
    report_path.write_text = lambda content, encoding="utf-8": setattr(report_path, "html", content)
    HTMLReportGenerator.generate(
        report_path,
        "test_parallel_filter",
        logs=logs,
        status="failed",
        error_msg="包含全部用户的 pytest traceback",
        suppress_error_box=failure_scope["suppress_error_box"],
        user_details={
            "userA": {"platform": "web", "display_platform": "web"},
            "userB": {"platform": "windows", "display_platform": "windows"},
        },
    )
    html = report_path.html
    assert 'class="error-entry" data-user="userA"' in html
    assert 'class="error-entry" data-user="userB"' in html
    assert "包含全部用户的 pytest traceback" not in html


def test_pure_assert_failure_is_global():
    """AW 外的直接 assert 失败应作为全局错误展示。"""
    ReportLogger.reset()
    logger = ReportLogger.get_current()
    logger.log_aw_call(
        aw_name="LoginAW",
        method="do_login",
        args={"user_id": "userA"},
        success=True,
        result={},
        duration_ms=10,
        is_business_method=True,
        call_id="success-1",
    )
    failure_scope = _record_test_failure(
        logger, "assert actual == expected", AssertionError()
    )
    error_log = next(
        log for log in logger.get_logs() if log.get("type") == "error"
    )

    assert "user_id" not in error_log
    assert failure_scope == {
        "error_user_id": "",
        "suppress_error_box": False,
    }
    html = HTMLReportGenerator._render_error(error_log)
    assert 'class="error-entry global-error"' in html
    assert 'data-user=""' in html

    report_path = SimpleNamespace(html="")
    report_path.write_text = lambda content, encoding="utf-8": setattr(report_path, "html", content)
    HTMLReportGenerator.generate(
        report_path,
        "test_direct_assert",
        logs=[error_log],
        status="failed",
        error_msg="assert actual == expected",
        user_details={"userA": {"platform": "web"}},
        error_user_id=failure_scope["error_user_id"],
        suppress_error_box=failure_scope["suppress_error_box"],
    )

    assert '<div class="error-box global-error">' in report_path.html
    assert "error-entry:not(.match-user):not(.global-error)" in report_path.html
    assert "error-box:not(.match-user):not(.global-error)" in report_path.html


def test_aw_failure_keeps_error_user_scope():
    """单用户 AW 失败的错误仍应跟随该用户过滤。"""
    ReportLogger.reset()
    logger = ReportLogger.get_current()
    raised = None
    try:
        FailingDemoAW(None, _user()).should_fail()
    except AssertionError as error:
        raised = error

    assert raised is not None

    failure_scope = _record_test_failure(
        logger, "完整 pytest traceback", raised
    )

    assert failure_scope == {
        "error_user_id": "userA",
        "suppress_error_box": False,
    }
    error_log = next(
        log for log in logger.get_logs() if log.get("type") == "error"
    )
    assert error_log["user_id"] == "userA"


def test_direct_assert_does_not_reuse_previous_failed_aw_user():
    """直接 assert 不应继承之前已被捕获的 AW 失败用户。"""
    ReportLogger.reset()
    logger = ReportLogger.get_current()
    logger.log_aw_call(
        aw_name="LoginAW",
        method="should_login_success",
        args={"user_id": "userA"},
        success=False,
        result={"error": "已被测试捕获的 AW 失败"},
        duration_ms=10,
        is_business_method=True,
        call_id="caught-failure",
    )

    raised = None
    try:
        assert False, "测试方法直接断言失败"
    except AssertionError as error:
        raised = error

    failure_scope = _record_test_failure(
        logger, "测试方法直接断言失败", raised
    )
    error_logs = [log for log in logger.get_logs() if log.get("type") == "error"]

    assert failure_scope["error_user_id"] == ""
    assert "user_id" not in error_logs[-1]


def test_user_tag_tooltip_shows_ip_account_name():
    """用户标签悬停 TIP 应显示 IP / 账号 / 姓名 / SN，缺省字段不渲染空行。"""
    group = {
        "ok": True,
        "rows": [],
        "children": [],
        "user_id": "userA",
        "user_platform": "windows",
        "title": "执行登录操作",
        "method_label": "LoginAW.do_login",
        "duration_ms": 10,
        "total_rows": 0,
        "fail_total": 0,
        "fail_rows": 0,
    }
    html = HTMLReportGenerator._render_group(
        group,
        "g1",
        user_details={
            "userA": {
                "platform": "windows",
                "display_platform": "windows",
                "ip": "10.8.3.21",
                "account": "138****2211",
                "name": "张三",
                "device_sn": "WIN-SN-001",
            }
        },
    )

    assert "u-tip" in html
    assert "10.8.3.21" in html
    assert "138****2211" in html
    assert "张三" in html
    assert "WIN-SN-001" in html
    assert "<b>SN</b>" in html


def test_user_tag_tooltip_omits_empty_sn():
    """用户 SN 为空时，悬停 TIP 不显示 SN 字段。"""
    group = {
        "ok": True,
        "rows": [],
        "children": [],
        "user_id": "userA",
        "user_platform": "windows",
        "title": "执行登录操作",
        "method_label": "LoginAW.do_login",
        "duration_ms": 10,
        "total_rows": 0,
        "fail_total": 0,
        "fail_rows": 0,
    }
    html = HTMLReportGenerator._render_group(
        group,
        "g1",
        user_details={
            "userA": {
                "platform": "windows",
                "display_platform": "windows",
                "device_sn": "",
            }
        },
    )

    assert "<b>SN</b>" not in html


def test_user_tag_tooltip_omits_missing_fields():
    """无 IP 的用户（如 API 用户）TIP 只显示有值的字段，不出现空行。"""
    group = {
        "ok": True,
        "rows": [],
        "children": [],
        "user_id": "userA_api",
        "user_platform": "",
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
                "account": "138****2211",
                "name": "张三",
            }
        },
    )

    assert "u-tip" in html
    assert "138****2211" in html
    assert "张三" in html


def test_user_tag_tooltip_absent_when_no_user_info():
    """用户信息全空时不渲染空 TIP。"""
    group = {
        "ok": True,
        "rows": [],
        "children": [],
        "user_id": "userA",
        "user_platform": "windows",
        "title": "执行登录操作",
        "method_label": "LoginAW.do_login",
        "duration_ms": 10,
        "total_rows": 0,
        "fail_total": 0,
        "fail_rows": 0,
    }
    html = HTMLReportGenerator._render_group(
        group,
        "g1",
        user_details={"userA": {"platform": "windows"}},
    )

    assert "u-tip" not in html
