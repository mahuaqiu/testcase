"""HooksResolver 测试。"""

import pytest
from common.hooks_resolver import HooksResolver


class TestHooksResolver:
    """HooksResolver 测试类。"""

    def test_resolve_with_no_case_hooks(self):
        """测试无用例级别 hooks 时返回平台默认。"""
        default_hooks = {
            "windows": {"setup": ["start_app"], "teardown": ["stop_app"]}
        }
        result = HooksResolver.resolve("windows", default_hooks, None)
        assert result == {"setup": ["start_app"], "teardown": ["stop_app"]}

    def test_resolve_with_complete_override(self):
        """测试完全覆盖。"""
        default_hooks = {
            "windows": {"setup": ["start_app", "login"], "teardown": ["logout", "stop_app"]}
        }
        case_hooks = {"setup": ["start_app"]}
        result = HooksResolver.resolve("windows", default_hooks, case_hooks)
        assert result["setup"] == ["start_app"]
        assert result["teardown"] == ["logout", "stop_app"]

    def test_resolve_with_append(self):
        """测试追加操作。"""
        default_hooks = {
            "windows": {"setup": ["start_app"], "teardown": ["stop_app"]}
        }
        case_hooks = {"setup": ["+login"]}
        result = HooksResolver.resolve("windows", default_hooks, case_hooks)
        assert result["setup"] == ["start_app", "login"]

    def test_resolve_with_remove(self):
        """测试移除操作。"""
        default_hooks = {
            "windows": {"setup": ["start_app", "login"], "teardown": ["logout", "stop_app"]}
        }
        case_hooks = {"teardown": ["-stop_app"]}
        result = HooksResolver.resolve("windows", default_hooks, case_hooks)
        assert result["teardown"] == ["logout"]

    def test_resolve_with_mixed(self):
        """测试混合操作。"""
        default_hooks = {
            "windows": {"setup": ["start_app", "login"], "teardown": ["logout", "stop_app"]}
        }
        case_hooks = {"setup": ["-login", "+accept_privacy"], "teardown": ["logout"]}
        result = HooksResolver.resolve("windows", default_hooks, case_hooks)
        assert result["setup"] == ["start_app", "accept_privacy"]
        assert result["teardown"] == ["logout"]

    def test_resolve_with_unknown_platform(self):
        """测试未知平台返回空。"""
        result = HooksResolver.resolve("unknown", {}, None)
        assert result == {"setup": [], "teardown": []}