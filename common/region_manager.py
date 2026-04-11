# common/region_manager.py
"""区域配置管理器（单例模式）。"""

import os
from typing import Dict, List, Optional
import yaml


class RegionManager:
    """管理各平台的布局区域配置。

    单例模式，启动时加载所有平台配置，后续直接查缓存。
    使用方式：
        region = RegionManager.get_instance().get_region("web", "meeting_main_2x2")
        # 返回 [0, 0, 960, 540]
    """

    _instance: Optional["RegionManager"] = None
    _configs: Dict[str, Dict[str, List[int]]] = {}  # {platform: {name: [x1,y1,x2,y2]}}

    def __new__(cls):
        """阻止直接实例化，必须通过 get_instance() 获取单例。"""
        if cls._instance is not None:
            raise RuntimeError("请使用 RegionManager.get_instance() 获取单例")
        return super().__new__(cls)

    @classmethod
    def get_instance(cls) -> "RegionManager":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_all()
        return cls._instance

    @classmethod
    def reload(cls) -> None:
        """重新加载所有配置（测试或热更新时使用）。"""
        cls._instance = None
        cls._configs = {}

    def _load_all(self) -> None:
        """加载所有平台的区域配置。"""
        # 配置目录：config/regions/
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "regions"
        )

        if not os.path.exists(config_dir):
            return

        for filename in os.listdir(config_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                platform = filename.rsplit(".", 1)[0]
                filepath = os.path.join(config_dir, filename)
                self._load_platform(platform, filepath)

    def _load_platform(self, platform: str, filepath: str) -> None:
        """加载单个平台的配置文件。"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            # 扁平结构，直接存储，验证坐标格式
            RegionManager._configs[platform] = {
                name: coords for name, coords in data.items()
                if isinstance(coords, list) and len(coords) == 4
                and all(isinstance(c, int) for c in coords)
            }
        except (FileNotFoundError, PermissionError, yaml.YAMLError):
            # 跳过加载失败的配置文件
            RegionManager._configs[platform] = {}

    def get_region(self, platform: str, name: str) -> Optional[List[int]]:
        """获取指定平台的区域坐标。

        Args:
            platform: 平台名（web/windows/android/ios/mac）
            name: 区域名称

        Returns:
            区域坐标 [x1, y1, x2, y2]，不存在返回 None
        """
        return RegionManager._configs.get(platform, {}).get(name)

    def list_regions(self, platform: str) -> List[str]:
        """列出指定平台的所有区域名称。"""
        return list(RegionManager._configs.get(platform, {}).keys())