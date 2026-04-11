# testcases/common/test_region_manager.py
"""RegionManager 单元测试。"""

import pytest
from common.region_manager import RegionManager


class TestRegionManager:
    """RegionManager 测试类。"""

    def test_get_instance_returns_singleton(self):
        """验证 get_instance 返回单例。"""
        instance1 = RegionManager.get_instance()
        instance2 = RegionManager.get_instance()
        assert instance1 is instance2

    def test_get_region_returns_coords(self):
        """验证 get_region 返回正确坐标。"""
        instance = RegionManager.get_instance()
        # 使用 web 平台测试数据
        region = instance.get_region("web", "meeting_main_2x2")
        assert region == [0, 0, 960, 540]

    def test_get_region_returns_none_for_unknown(self):
        """验证未知区域返回 None。"""
        instance = RegionManager.get_instance()
        region = instance.get_region("web", "unknown_region")
        assert region is None

    def test_get_region_returns_none_for_unknown_platform(self):
        """验证未知平台返回 None。"""
        instance = RegionManager.get_instance()
        region = instance.get_region("unknown_platform", "meeting_main")
        assert region is None

    def test_list_regions(self):
        """验证 list_regions 返回区域名称列表。"""
        instance = RegionManager.get_instance()
        regions = instance.list_regions("web")
        assert "meeting_main_2x2" in regions

    def test_reload_clears_cache(self):
        """验证 reload 清除缓存。"""
        instance1 = RegionManager.get_instance()
        RegionManager.reload()
        instance2 = RegionManager.get_instance()
        assert instance1 is not instance2