"""Hooks 解析和执行测试。"""

from types import SimpleNamespace

import pytest

from common.hooks_resolver import HooksResolver
from conftest import (
    HookFailureError,
    _execute_hooks,
    _get_conftest_hook_layers,
    _resolve_final_hooks,
)


class _SilentLogger:
    """测试用日志对象。"""

    def log_step(self, message):
        pass

    def log_error(self, message, user_id=None):
        """兼容 log_error(user_id=...)"""
        pass


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

        def log_error(self, message, user_id=None):
            """兼容 log_error(user_id=...)"""
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


# ── 多参数 hook（List 参数）测试 ─────────────────────────────────────────


def test_execute_hooks_supports_list_args_for_multi_param_hook(monkeypatch):
    """列表参数应按位置参数展开，支持多参数函数。"""
    calls = []

    class User:
        """测试用用户对象。"""

        def do_set_waiting_room(self, conference_id, chair_password, enable):
            calls.append((conference_id, chair_password, enable))

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    _execute_hooks(
        User(),
        [{"set_waiting_room": ["cid-001", "pwd", True]}],
        hook_type="setup",
    )

    assert calls == [("cid-001", "pwd", True)]


def test_execute_hooks_list_args_mismatch_raises(monkeypatch):
    """列表参数与目标方法签名不匹配时应抛 HookFailureError，不静默降级。"""
    class User:
        """测试用用户对象。"""

        def do_login(self):
            pass  # 无参方法，收到 2 个位置参数必然失败

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    with pytest.raises(HookFailureError):
        _execute_hooks(User(), [{"login": ["a", "b"]}], hook_type="setup")


def test_execute_hooks_single_arg_still_falls_back_to_no_arg(monkeypatch):
    """单值参数绑定失败时仍降级为无参调用（布尔标记写法）。"""
    calls = []

    class User:
        """测试用用户对象。"""

        def do_leave(self):
            calls.append("leave")

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    _execute_hooks(User(), [{"leave": True}], hook_type="teardown")

    assert calls == ["leave"]


# ── app_type 注入测试 ─────────────────────────────────────────


def test_execute_hooks_injects_app_type_when_method_has_param(monkeypatch):
    """方法签名含 app_type 且配置有值时，应自动以 kwargs 注入。"""
    calls = []

    class User:
        """测试用用户对象。"""

        def do_start_app(self, app_type=None):
            calls.append(app_type)

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    _execute_hooks(User(), ["start_app"], app_type="TestAapp1")

    assert calls == ["TestAapp1"]


def test_execute_hooks_app_type_combined_with_positional_arg(monkeypatch):
    """位置参数与 app_type 注入可组合。"""
    calls = []

    class User:
        """测试用用户对象。"""

        def do_start_app(self, browser, app_type=None):
            calls.append((browser, app_type))

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    _execute_hooks(User(), [{"start_app": "edge"}], app_type="TestAapp1")

    assert calls == [("edge", "TestAapp1")]


def test_execute_hooks_skips_app_type_when_method_lacks_param(monkeypatch):
    """方法签名没有 app_type 参数时不应传，即使配置有值。"""
    calls = []

    class User:
        """测试用用户对象。"""

        def do_start_app(self):
            calls.append("ok")

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    _execute_hooks(User(), ["start_app"], app_type="TestAapp1")

    assert calls == ["ok"]


def test_execute_hooks_skips_app_type_when_not_configured(monkeypatch):
    """平台未配置 app_type 时（None），方法即使有该参数也不传。"""
    calls = []

    class User:
        """测试用用户对象。"""

        def do_start_app(self, app_type=None):
            calls.append(app_type)

    monkeypatch.setattr("conftest.ReportLogger.get_current", lambda: _SilentLogger())

    _execute_hooks(User(), ["start_app"], app_type=None)

    assert calls == [None]


def test_app_type_passthrough_from_platform_defaults():
    """resolve 结果应透传平台默认层的 app_type；未配置的平台无该键。"""
    defaults = {
        "windows": {
            "setup": ["start_app"],
            "teardown": ["stop_app"],
            "app_type": "TestAapp1",
        },
        "web": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    case_hooks = {"setup": ["+login"]}

    result_win = HooksResolver.resolve("windows", defaults, case_hooks)
    result_web = HooksResolver.resolve("web", defaults, case_hooks)

    assert result_win["app_type"] == "TestAapp1"
    assert "app_type" not in result_web


# ── 目录 conftest hooks 层测试 ─────────────────────────────────────────


def test_conftest_layer_merges_between_defaults_and_marker():
    """目录 conftest 层位于平台默认与用例标记层之间。

    setup 全部按层顺序尾插；teardown 用例标记层前插（先执行），
    conftest 层与平台默认合并后按顺序执行。
    """
    defaults = {"web": {"setup": ["start_app"], "teardown": ["stop_app"]}}
    conftest_hooks = {"setup": ["+prepare_env"], "teardown": ["+cleanup_env"]}
    case_hooks = {"setup": ["+login"], "teardown": ["+leave"]}
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [conftest_hooks], case_hooks)

    assert result["setup"] == ["start_app", "prepare_env", "login"]
    assert result["teardown"] == ["leave", "stop_app", "cleanup_env"]


def test_marker_teardown_additions_keep_declared_order_when_prepended():
    """用例标记层多个 teardown 增量前插时保持声明顺序。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    case_hooks = {"teardown": ["+leave", "+stoprecordingdesktop"]}
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [], case_hooks)

    assert result["teardown"] == ["leave", "stoprecordingdesktop", "stop_app"]


def test_marker_user_layer_teardown_prepends_before_global_layer():
    """用例标记层内，用户键 teardown 增量前插到全局层增量之前。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    case_hooks = {
        "teardown": ["+global_cleanup"],
        "userA": {"teardown": ["+user_cleanup"]},
    }
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [], case_hooks)

    assert result["teardown"] == ["user_cleanup", "global_cleanup", "stop_app"]


def test_conftest_layer_supports_user_and_platform_keys():
    """目录 conftest 层支持与用例标记同构的键结构（用户/平台键）。"""
    defaults = {
        "web": {"setup": ["start_app"], "teardown": ["stop_app"]},
        "mac": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    conftest_hooks = {
        "web": {"setup": ["+conftest_platform"]},
        "userA": {"setup": ["+conftest_user"]},
    }
    case_hooks = {"userA": {"setup": ["+case_user"]}}

    user_a = SimpleNamespace(platform="web")
    user_b = SimpleNamespace(platform="web")

    result_a = _resolve_final_hooks(user_a, "userA", defaults, [conftest_hooks], case_hooks)
    result_b = _resolve_final_hooks(user_b, "userB", defaults, [conftest_hooks], case_hooks)
    result_mac = _resolve_final_hooks(
        SimpleNamespace(platform="mac"), "userA", defaults, [conftest_hooks], case_hooks
    )

    assert result_a["setup"] == ["start_app", "conftest_platform", "conftest_user", "case_user"]
    assert result_b["setup"] == ["start_app", "conftest_platform"]
    # 用户键跨平台生效（与用例标记层语义一致），仅平台键受平台限制
    assert result_mac["setup"] == ["start_app", "conftest_user", "case_user"]


def test_conftest_layer_teardown_removal_applies_to_base():
    """目录 conftest 层的 - 移除作用于平台默认，而非前插。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    conftest_hooks = {"teardown": ["-stop_app"]}
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [conftest_hooks], {})

    assert result["teardown"] == []


def test_app_type_survives_two_pass_compose():
    """两遍合并后 app_type 仍从平台默认透传到最终结果。"""
    defaults = {
        "windows": {
            "setup": ["start_app"],
            "teardown": ["stop_app"],
            "app_type": "TestAapp1",
        },
    }
    conftest_hooks = {"setup": ["+prepare_env"]}
    case_hooks = {"userA": {"teardown": ["+leave"]}}
    user = SimpleNamespace(platform="windows")

    result = _resolve_final_hooks(user, "userA", defaults, [conftest_hooks], case_hooks)

    assert result["app_type"] == "TestAapp1"
    assert result["teardown"] == ["leave", "stop_app"]


# ── app_type 分层覆盖测试 ─────────────────────────────────────────


def test_case_marker_app_type_overrides_platform_default():
    """用例标记层全局 app_type 覆盖平台默认配置。"""
    defaults = {"windows": {"app_type": "FromConfig"}}
    case_hooks = {"app_type": "FromCase"}

    result = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userA")

    assert result["app_type"] == "FromCase"


def test_case_app_type_without_platform_default():
    """平台默认未配置 app_type 时，用例层声明同样生效。"""
    defaults = {"web": {"setup": ["start_app"]}}

    result = HooksResolver.resolve("web", defaults, {"app_type": "FromCase"})

    assert result["app_type"] == "FromCase"


def test_case_app_type_none_keeps_base():
    """用例层 app_type 为 None 视为未声明，不覆盖平台默认。"""
    defaults = {"windows": {"app_type": "FromConfig"}}

    result = HooksResolver.resolve("windows", defaults, {"app_type": None})

    assert result["app_type"] == "FromConfig"


def test_case_platform_key_app_type_scoped_and_beats_global():
    """平台键 app_type 只对该平台生效，且覆盖同层全局值。"""
    defaults = {"windows": {}, "web": {}}
    case_hooks = {"app_type": "FromGlobal", "windows": {"app_type": "FromWindows"}}

    result_win = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userA")
    result_web = HooksResolver.resolve("web", defaults, case_hooks, user_id="userA")

    assert result_win["app_type"] == "FromWindows"
    assert result_web["app_type"] == "FromGlobal"


def test_case_user_key_app_type_beats_platform_key():
    """app_type 作用域优先级：用户键 > 平台键 > 全局。"""
    defaults = {"windows": {}}
    case_hooks = {
        "app_type": "FromGlobal",
        "windows": {"app_type": "FromWindows"},
        "userA": {"app_type": "FromUser"},
    }

    result_a = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userA")
    result_b = HooksResolver.resolve("windows", defaults, case_hooks, user_id="userB")

    assert result_a["app_type"] == "FromUser"
    assert result_b["app_type"] == "FromWindows"


def test_app_type_layered_override_across_layers():
    """app_type 分层覆盖：config.yaml 平台默认 < conftest 层 < 用例标记层。"""
    defaults = {"windows": {"app_type": "FromConfig"}}
    conftest_hooks = {"app_type": "FromConftest"}
    user = SimpleNamespace(platform="windows")

    result_conftest = _resolve_final_hooks(user, "userA", defaults, [conftest_hooks], {})
    result_case = _resolve_final_hooks(
        user, "userA", defaults, [conftest_hooks], {"app_type": "FromCase"}
    )
    result_no_conftest = _resolve_final_hooks(user, "userA", defaults, [], {})

    assert result_conftest["app_type"] == "FromConftest"
    assert result_case["app_type"] == "FromCase"
    assert result_no_conftest["app_type"] == "FromConfig"


def test_conftest_platform_key_app_type_applies_to_platform_users():
    """conftest 层平台键中的 app_type 只作用于对应平台用户。"""
    defaults = {"windows": {"app_type": "FromConfig"}, "mac": {}}
    conftest_hooks = {"windows": {"app_type": "FromConftest"}}

    result_win = _resolve_final_hooks(
        SimpleNamespace(platform="windows"), "userA", defaults, [conftest_hooks], {}
    )
    result_mac = _resolve_final_hooks(
        SimpleNamespace(platform="mac"), "userA", defaults, [conftest_hooks], {}
    )

    assert result_win["app_type"] == "FromConftest"
    assert "app_type" not in result_mac


def test_validate_user_keys_allows_app_type_key():
    """app_type 是标量配置键而非用户键，校验时不应报未声明用户。"""
    HooksResolver.validate_user_keys(
        {"app_type": "FromCase", "userA": {"teardown": ["+leave"]}},
        known_user_ids=["userA"],
        known_platforms=["windows"],
    )


def test_split_case_hooks_returns_app_type_separately():
    """split_case_hooks 应单独返回 app_type，不混入用户键。"""
    global_hooks, platform_hooks, user_hooks, app_type = HooksResolver.split_case_hooks(
        {"app_type": "FromCase", "setup": ["+login"], "windows": {"app_type": "FromWindows"}},
        known_platforms=["windows"],
    )

    assert app_type == "FromCase"
    assert global_hooks == {"setup": ["+login"]}
    assert user_hooks == {}
    assert platform_hooks["windows"]["app_type"] == "FromWindows"


def test_get_conftest_hook_layers_collects_all_levels(tmp_path):
    """应收集所有层级目录 conftest 的 hooks，按从外到内排序。"""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    (outer / "conftest.py").write_text(
        "def get_hooks():\n"
        "    return {'setup': ['+from_outer']}\n",
        encoding="utf-8",
    )
    (inner / "conftest.py").write_text(
        "def get_hooks():\n"
        "    return {'setup': ['+from_inner']}\n",
        encoding="utf-8",
    )
    node = SimpleNamespace(fspath=str(inner / "test_x.py"))

    layers = _get_conftest_hook_layers(node)

    assert layers == [{"setup": ["+from_outer"]}, {"setup": ["+from_inner"]}]


def test_get_conftest_hook_layers_skips_non_dict_result(tmp_path):
    """get_hooks 返回非字典的层按空处理，不影响其它层。"""
    (tmp_path / "conftest.py").write_text(
        "def get_hooks():\n"
        "    return ['not', 'a', 'dict']\n",
        encoding="utf-8",
    )
    node = SimpleNamespace(fspath=str(tmp_path / "test_x.py"))

    assert _get_conftest_hook_layers(node) == []


def test_get_conftest_hook_layers_empty_when_not_defined(tmp_path):
    """目录 conftest 未定义 get_hooks 时返回空层列表。"""
    (tmp_path / "conftest.py").write_text(
        "def get_namespace():\n"
        "    return 'web_public'\n",
        encoding="utf-8",
    )
    node = SimpleNamespace(fspath=str(tmp_path / "test_x.py"))

    assert _get_conftest_hook_layers(node) == []


def test_multi_level_conftest_layers_merge_inner_overrides_outer():
    """多级 conftest 全部生效：不重复的都执行，重复的按 外层 < 内层 < 用例 覆盖。

    - setup：外层增量 +outer_hook 全部保留，内层无前缀覆盖字符串只覆盖
      到此前累积的 setup；用例层再增量追加。
    - teardown：内层 - 移除外层声明的 hook。
    """
    defaults = {
        "web": {"setup": ["start_app"], "teardown": ["stop_app", "report"]},
    }
    outer_layer = {"setup": ["+outer_hook"], "teardown": ["+outer_cleanup"]}
    inner_layer = {"teardown": ["-outer_cleanup"]}
    case_hooks = {"setup": ["+case_hook"]}
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [outer_layer, inner_layer], case_hooks)

    # 不重复的全部执行：平台默认 + 外层 + 内层 + 用例层
    assert result["setup"] == ["start_app", "outer_hook", "case_hook"]
    # 内层 - 移除外层增量
    assert result["teardown"] == ["stop_app", "report"]


def test_multi_level_conftest_prefix_override_priority():
    """重复声明时优先级：用例层 > 内层 conftest > 外层 conftest > config.yaml。

    以无前缀字符串完全覆盖为手段验证：内层覆盖掉外层与平台默认的 setup，
    用例层再覆盖内层。
    """
    defaults = {
        "web": {"setup": ["start_app"], "teardown": ["stop_app"]},
    }
    outer_layer = {"setup": ["+outer_extra"]}
    inner_layer = {"setup": ["inner_setup"]}
    case_hooks = {"setup": ["case_setup"]}
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [outer_layer, inner_layer], case_hooks)

    # 内层无前缀覆盖：只留 inner_setup；用例层无前缀覆盖：只留 case_setup
    assert result["setup"] == ["case_setup"]


def test_multi_level_conftest_teardown_order_with_marker_prepend():
    """多级 conftest teardown 按外→内顺序执行，用例层 teardown 增量仍最前。"""
    defaults = {"web": {"teardown": ["stop_app"]}}
    outer_layer = {"teardown": ["+outer_cleanup"]}
    inner_layer = {"teardown": ["+inner_cleanup"]}
    case_hooks = {"teardown": ["+leave"]}
    user = SimpleNamespace(platform="web")

    result = _resolve_final_hooks(user, "userA", defaults, [outer_layer, inner_layer], case_hooks)

    assert result["teardown"] == ["leave", "stop_app", "outer_cleanup", "inner_cleanup"]
