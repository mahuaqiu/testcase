# common/region_manager.py
"""区域配置管理器（单例模式）。"""

import os
from typing import Any, Dict, List, Optional
import yaml

from common.report_logger import ReportLogger


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
        """加载单个平台的配置文件。

        加载失败、顶层格式错误或条目非法时写 warning 到报告日志，
        不中断启动；非法配置对应的区域不可用。
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (FileNotFoundError, PermissionError, yaml.YAMLError) as e:
            self._warn(f"区域配置加载失败，该平台所有区域不可用: {filepath} - {e}")
            RegionManager._configs[platform] = {}
            return

        if not isinstance(data, dict):
            self._warn(
                f"区域配置顶层格式错误，应为映射（区域名: [x1,y1,x2,y2]），"
                f"实际为 {type(data).__name__}: {filepath}"
            )
            RegionManager._configs[platform] = {}
            return

        # 扁平结构，逐条校验坐标格式，非法条目忽略并告警
        valid: Dict[str, List[int]] = {}
        for name, coords in data.items():
            reason = self._invalid_reason(coords)
            if reason:
                self._warn(
                    f"区域配置条目非法已忽略: {platform}.{name} = {coords!r}，{reason}"
                )
            else:
                valid[name] = coords
        RegionManager._configs[platform] = valid

    @staticmethod
    def _invalid_reason(coords: Any) -> str:
        """返回坐标条目非法的原因，合法返回空字符串。"""
        if not isinstance(coords, list):
            return f"应为列表 [x1,y1,x2,y2]，实际为 {type(coords).__name__}"
        if len(coords) != 4:
            return f"应为 4 个坐标值，实际为 {len(coords)} 个"
        if not all(isinstance(c, int) for c in coords):
            return f"坐标应为整数，实际为 {coords!r}"
        return ""

    @staticmethod
    def _warn(message: str) -> None:
        """写 warning 到报告日志（同时输出到控制台，便于实时定位）。"""
        try:
            ReportLogger.get_current().log_aw_message(
                message=message, aw_name="RegionManager", level="warning"
            )
        except Exception:
            pass  # 日志失败不影响配置加载

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