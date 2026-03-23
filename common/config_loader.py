"""配置加载器。

支持多层级配置合并：
1. config.yaml（基础配置）
2. config.local.yaml（本地覆盖）
3. 环境变量（最高优先级）
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigLoader:
    """配置加载器，支持环境变量覆盖。

    单例模式，确保全局配置一致性。

    Usage:
        loader = ConfigLoader()
        config = loader.load()
        value = loader.get("resource_manager.base_url")
    """

    _instance: Optional["ConfigLoader"] = None
    _config: Dict[str, Any] = {}
    _loaded: bool = False

    def __new__(cls) -> "ConfigLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: str = "config.yaml") -> Dict[str, Any]:
        """加载配置文件。

        按优先级依次加载：config.yaml → config.local.yaml → 环境变量。

        Args:
            config_path: 配置文件路径，默认为 config.yaml。

        Returns:
            合并后的配置字典。
        """
        if self._loaded:
            return self._config

        # 1. 加载基础配置（使用项目根目录的绝对路径）
        base_path = Path(__file__).parent.parent / config_path
        if base_path.exists():
            self._config = self._load_yaml(base_path)

        # 2. 加载本地配置覆盖（使用项目根目录的绝对路径）
        local_path = Path(__file__).parent.parent / "config.local.yaml"
        if local_path.exists():
            local_config = self._load_yaml(local_path)
            self._deep_merge(self._config, local_config)

        # 3. 环境变量覆盖
        self._apply_env_overrides()

        self._loaded = True
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值。

        支持点分隔的嵌套 key，如 "resource_manager.base_url"。

        Args:
            key: 配置键，支持嵌套。
            default: 默认值。

        Returns:
            配置值，不存在则返回默认值。
        """
        if not self._loaded:
            self.load()

        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_resource_manager_config(self) -> Dict[str, Any]:
        """获取资源管理配置。

        Returns:
            资源管理配置字典。
        """
        return self.get("resource_manager", {})

    def get_testagent_config(self) -> Dict[str, Any]:
        """获取 testagent 配置。

        Returns:
            testagent 配置字典。
        """
        return self.get("testagent", {})

    def reset(self) -> None:
        """重置配置（主要用于测试）。"""
        self._config = {}
        self._loaded = False

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """加载 YAML 文件。

        Args:
            path: 文件路径。

        Returns:
            解析后的字典。
        """
        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            # yaml 未安装时返回空字典
            return {}

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """深度合并字典。

        将 override 合并到 base 中，嵌套字典递归合并。

        Args:
            base: 基础字典（会被修改）。
            override: 覆盖字典。
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _apply_env_overrides(self) -> None:
        """应用环境变量覆盖。"""
        # 资源管理服务地址
        if os.environ.get("RESOURCE_MANAGER_URL"):
            self._config.setdefault("resource_manager", {})["base_url"] = (
                os.environ["RESOURCE_MANAGER_URL"]
            )

        # testagent 服务地址
        if os.environ.get("TESTAGENT_URL"):
            self._config.setdefault("testagent", {})["base_url"] = (
                os.environ["TESTAGENT_URL"]
            )

        # 超时时间
        if os.environ.get("RESOURCE_MANAGER_TIMEOUT"):
            self._config.setdefault("resource_manager", {})["timeout"] = int(
                os.environ["RESOURCE_MANAGER_TIMEOUT"]
            )