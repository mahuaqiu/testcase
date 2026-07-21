"""Hooks 解析和执行测试。"""

from common.hooks_resolver import HooksResolver
from conftest import _execute_hooks


def test_mixed_dict_and_add_hooks_keep_all_items_in_declared_order():
    """混合字典和增量 hook 时，应保留所有项并按声明顺序排列。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    case_hooks = {
        "teardown": ["+stoprecordingdesktop", "+stop_app", {"leave": True}]
    }

    result = HooksResolver.resolve("web", defaults, case_hooks)

    assert result["teardown"] == [
        "stoprecordingdesktop",
        "stop_app",
        {"leave": True},
    ]


def test_mixed_hooks_keep_dict_position_when_dict_is_first():
    """字典 hook 放在第一项时，应按第一项执行。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    case_hooks = {
        "teardown": [{"leave": True}, "+stoprecordingdesktop", "+stop_app"]
    }

    result = HooksResolver.resolve("web", defaults, case_hooks)

    assert result["teardown"] == [
        {"leave": True},
        "stoprecordingdesktop",
        "stop_app",
    ]


def test_unprefixed_string_still_replaces_case_hooks():
    """无前缀字符串仍保持原有的完全覆盖语义。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    case_hooks = {"teardown": ["custom_hook", "+stoprecordingdesktop"]}

    result = HooksResolver.resolve("web", defaults, case_hooks)

    assert result["teardown"] == ["custom_hook"]


def test_unprefixed_dict_still_replaces_case_hooks():
    """纯字典 hook 列表仍保持原有的完全覆盖语义。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    case_hooks = {"teardown": [{"custom_hook": "value"}]}

    result = HooksResolver.resolve("web", defaults, case_hooks)

    assert result["teardown"] == [{"custom_hook": "value"}]


def test_execute_hooks_preserves_order_and_supports_boolean_flag_for_no_arg_hook(monkeypatch):
    """执行器应按列表顺序调用，并兼容无参 hook 的布尔标记。"""
    calls = []

    class Logger:
        """测试用日志对象。"""

        def log_step(self, message):
            pass

        def log_error(self, message):
            pass

    class User:
        """测试用用户对象。"""

        def do_leave(self):
            calls.append("leave")

        def do_stoprecordingdesktop(self):
            calls.append("stoprecordingdesktop")

        def do_stop_app(self):
            calls.append("stop_app")

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: Logger())

    _execute_hooks(
        User(),
        [
            {"leave": True},
            "stoprecordingdesktop",
            "stop_app",
        ],
        hook_type="teardown",
    )

    assert calls == ["leave", "stoprecordingdesktop", "stop_app"]
