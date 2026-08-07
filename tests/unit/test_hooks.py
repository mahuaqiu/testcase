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


# ── 按用户/平台分层 hooks 测试 ─────────────────────────────────────────


def test_only_user_key_applies_to_that_user():
    """仅 userA 键：userA 增量，userB 仅默认。"""
    defaults = {
        "windows": {"setup": ["start_app"], "teardown": ["stop_app"]},
        "mac": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    case_hooks = {
        "userA": {"setup": ["+login"]},
    }

    result_a = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userA")
    result_b = HooksResolver.resolve("mac", defaults, case_hooks, user_id="userB")

    assert result_a["setup"] == ["start_app", "login"]
    assert result_b["setup"] == ["start_app"]
    assert result_a["teardown"] == ["stop_app"]
    assert result_b["teardown"] == ["stop_app"]


def test_global_plus_user_layer_priority():
    """全局 + user 叠加：用户键优先。"""
    defaults = {
        "web": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    case_hooks = {
        "setup": ["+login"],
        "userA": {"setup": ["+extra_login"], "teardown": ["-stop_app"]},
    }

    result_a = HooksResolver.resolve("web", defaults, case_hooks, user_id="userA")
    result_b = HooksResolver.resolve("web", defaults, case_hooks, user_id="userB")

    assert result_a["setup"] == ["start_app", "login", "extra_login"]
    assert result_a["teardown"] == []
    assert result_b["setup"] == ["start_app", "login"]
    assert result_b["teardown"] == ["stop_app"]


def test_platform_key_affects_only_that_platform():
    """平台键 windows 只影响 windows 用户，不影响 mac。"""
    defaults = {
        "windows": {"setup": ["start_app"], "teardown": ["stop_app"]},
        "mac": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    case_hooks = {
        "windows": {"setup": ["+login"]},
        "mac": {"teardown": ["-stop_app"]},
    }

    result_win = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userA")
    result_mac = HooksResolver.resolve("mac", defaults, case_hooks, user_id="userB")

    assert result_win["setup"] == ["start_app", "login"]
    assert result_win["teardown"] == ["stop_app"]
    assert result_mac["setup"] == ["start_app"]
    assert result_mac["teardown"] == []


def test_user_key_overrides_platform_key():
    """用户键优先于平台键。"""
    defaults = {
        "windows": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    case_hooks = {
        "windows": {"setup": ["+login"]},
        "userA": {"setup": ["+extra"], "teardown": ["-stop_app"]},
    }

    result = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userA")

    assert result["setup"] == ["start_app", "login", "extra"]
    assert result["teardown"] == []


def test_user_a_does_not_affect_user_a_api():
    """userA 不影响 userA_api；userA_api 显式覆盖生效。"""
    defaults = {
        "web": {"setup": ["start_app"], "teardown": ["stop_app"]},
        "api": {"setup": [], "teardown": ["cancel_all_meetings"]},
    }
    case_hooks = {
        "userA": {"setup": ["+login"]},
        "userA_api": {"teardown": ["-cancel_all_meetings"]},
    }

    result_ui = HooksResolver.resolve("web", defaults, case_hooks, user_id="userA")
    result_api = HooksResolver.resolve("api", defaults, case_hooks, user_id="userA_api")

    assert result_ui["setup"] == ["start_app", "login"]
    assert result_api["setup"] == []
    assert result_api["teardown"] == []


def test_validate_user_keys_raises_on_unknown_user():
    """未知 user 键应直接抛错。"""
    case_hooks = {
        "userC": {"setup": ["+login"]},
    }
    known_users = ["userA", "userB", "userA_api", "userB_api"]
    known_platforms = ["web", "windows", "mac", "api"]

    try:
        HooksResolver.validate_user_keys(case_hooks, known_users, known_platforms)
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "userC" in str(e)
        assert "合法用户" in str(e)


def test_validate_user_keys_passes_for_valid_users():
    """合法用户键应通过校验。"""
    case_hooks = {
        "userA": {"setup": ["+login"]},
        "userB_api": {"teardown": ["-cancel_all_meetings"]},
    }
    known_users = ["userA", "userB", "userA_api", "userB_api"]
    known_platforms = ["web", "windows", "mac", "api"]

    # 不应抛错
    HooksResolver.validate_user_keys(case_hooks, known_users, known_platforms)


def test_mixed_plus_minus_dict_in_user_layer():
    """用户层混合 +/−/字典格式仍按既有规则工作。"""
    defaults = {
        "web": {"teardown": ["stop_app"]},
    }
    case_hooks = {
        "userA": {
            "teardown": ["+stoprecordingdesktop", "+stop_app", {"leave": True}]
        },
    }

    result = HooksResolver.resolve("web", defaults, case_hooks, user_id="userA")

    assert result["teardown"] == [
        "stoprecordingdesktop",
        "stop_app",
        {"leave": True},
    ]
