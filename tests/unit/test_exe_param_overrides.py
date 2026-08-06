"""exeParam 和平台 Hooks 配置覆盖测试。"""

from pathlib import Path

from common.hooks_resolver import HooksResolver
from conftest import _apply_exe_param_overrides


def test_exe_param_short_form_overrides_resource_manager_values():
    """顶层 namespace 和 env_auth 应覆盖资源管理配置。"""
    config = {
        "env": "test",
        "resource_manager": {
            "namespace": "from-config",
            "env_auth": "config-key",
            "timeout": 30,
            "retry": {"max_wait_seconds": 900},
        },
    }

    _apply_exe_param_overrides(
        config,
        {"version": "xxx", "namespace": "1111", "env_auth": "param-key"},
    )

    assert config["resource_manager"]["namespace"] == "1111"
    assert config["resource_manager"]["env_auth"] == "param-key"
    assert config["resource_manager"]["timeout"] == 30
    assert config["version"] == "xxx"


def test_exe_param_nested_resource_manager_uses_deep_merge():
    """嵌套 resource_manager 参数应只覆盖指定字段。"""
    config = {
        "resource_manager": {
            "namespace": "from-config",
            "env_auth": "config-key",
            "retry": {"max_wait_seconds": 900, "retry_interval": 15},
        }
    }

    _apply_exe_param_overrides(
        config,
        {"resource_manager": {"namespace": "nested", "retry": {"retry_interval": 1}}},
    )

    assert config["resource_manager"]["namespace"] == "nested"
    assert config["resource_manager"]["env_auth"] == "config-key"
    assert config["resource_manager"]["retry"] == {
        "max_wait_seconds": 900,
        "retry_interval": 1,
    }


def test_harmony_platforms_have_default_hooks():
    """Harmony PC 和移动端应解析到默认启动与关闭 hooks。"""
    import yaml

    config_path = Path(__file__).parents[2] / "config.yaml"
    with config_path.open(encoding="utf-8") as config_file:
        defaults = yaml.safe_load(config_file)["hooks"]

    for platform in ("harmony_pc", "harmony_mobile"):
        assert HooksResolver.resolve(platform, defaults) == {
            "setup": ["start_app"],
            "teardown": ["stop_app"],
        }
