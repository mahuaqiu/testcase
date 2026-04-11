# 布局区域模板系统设计文档

## 背景

多画面会场布局检查场景中，需要精确判断某个区域内的内容是否正确。现有方案无法指定区域，只能全屏查找，导致多画面场景下的布局验证困难。

testagent 已新增 `region` 参数（格式 `[x1, y1, x2, y2]`），支持限制 OCR/图像识别在指定矩形区域内执行。

本设计目标：提供区域模板系统，支持按名称引用区域坐标，不同平台配置独立，入侵现有代码最少。

## 设计方案

### 1. 文件结构

```
config/
├── config.yaml              # 主配置（不变）
├── regions/                 # 新增：区域配置目录
│   ├── web.yaml             # Web 平台区域
│   ├── windows.yaml         # Windows 平台区域
│   ├── android.yaml         # Android 平台区域
│   ├── ios.yaml             # iOS 平台区域
│   └── mac.yaml             # Mac 平台区域

common/
├── region_manager.py        # 新增：区域管理器（单例）
├── ...                      # 其他文件不变

aw/
├── base_aw.py               # 改动：添加 _resolve_region 方法
├── ...                      # 其他文件不变
```

### 2. 区域配置文件格式

每个平台的 `regions/*.yaml` 采用扁平结构：

```yaml
# config/regions/web.yaml
# Web 平台布局区域配置
# 格式：区域名称: [x1, y1, x2, y2]

# 2x2 布局
meeting_main_2x2: [0, 0, 960, 540]
meeting_sub1_2x2: [960, 0, 1920, 540]
meeting_sub2_2x2: [0, 540, 960, 1080]
meeting_sub3_2x2: [960, 540, 1920, 1080]

# 3x3 布局
meeting_main_3x3: [0, 0, 640, 360]
meeting_sub1_3x3: [640, 0, 1280, 360]

# 画廊模式（全屏）
meeting_gallery: [0, 0, 1920, 1080]

# 共享屏幕区域
share_local: [0, 540, 1920, 1080]
```

命名规范：`{场景}_{描述}_{布局}`，便于识别。

### 3. RegionManager 实现

单例模式，启动时加载所有平台配置，后续直接查缓存。

```python
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
    _config_dir: str = ""
    
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
        self._config_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "regions"
        )
        
        if not os.path.exists(self._config_dir):
            return
        
        for filename in os.listdir(self._config_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                platform = filename.rsplit(".", 1)[0]
                filepath = os.path.join(self._config_dir, filename)
                self._load_platform(platform, filepath)
    
    def _load_platform(self, platform: str, filepath: str) -> None:
        """加载单个平台的配置文件。"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # 扁平结构，直接存储
        self._configs[platform] = {
            name: coords for name, coords in data.items()
            if isinstance(coords, list) and len(coords) == 4
        }
    
    def get_region(self, platform: str, name: str) -> Optional[List[int]]:
        """获取指定平台的区域坐标。
        
        Args:
            platform: 平台名（web/windows/android/ios/mac）
            name: 区域名称
            
        Returns:
            区域坐标 [x1, y1, x2, y2]，不存在返回 None
        """
        return self._configs.get(platform, {}).get(name)
    
    def list_regions(self, platform: str) -> List[str]:
        """列出指定平台的所有区域名称。"""
        return list(self._configs.get(platform, {}).keys())
```

### 4. BaseAW 改动

#### 4.1 新增 `_resolve_region` 方法

```python
# base_aw.py 新增方法
def _resolve_region(self, region) -> Optional[List[int]]:
    """解析区域参数，支持字符串名称或坐标数组。
    
    Args:
        region: 区域参数，可以是：
            - None: 不限制区域（全屏）
            - List[int]: 直接坐标 [x1, y1, x2, y2]
            - str: 区域名称，自动查找配置
            
    Returns:
        区域坐标 [x1, y1, x2, y2]，或 None
    """
    if region is None:
        return None
    if isinstance(region, list):
        return region  # 直接传坐标数组
    
    # 字符串名称 → 查配置
    from common.region_manager import RegionManager
    platform = self.user.platform if self.user else ""
    return RegionManager.get_instance().get_region(platform, region)
```

#### 4.2 修改 `_ocr_params` 和 `_image_params`

使用 `_resolve_region` 解析 region 参数：

```python
def _ocr_params(self, kwargs: dict) -> dict:
    params = {
        "timeout": kwargs.get("timeout", 5) * 1000,
        "index": kwargs.get("index", 0),
    }
    if "offset" in kwargs:
        params["offset"] = kwargs["offset"]
    # 使用 _resolve_region 解析
    resolved = self._resolve_region(kwargs.get("region"))
    if resolved:
        params["region"] = resolved
    return params

def _image_params(self, kwargs: dict) -> dict:
    params = {
        "timeout": kwargs.get("timeout", 5) * 1000,
        "threshold": kwargs.get("confidence", 0.8),
    }
    if "index" in kwargs:
        params["index"] = kwargs["index"]
    if "offset" in kwargs:
        params["offset"] = kwargs["offset"]
    # 使用 _resolve_region 解析
    resolved = self._resolve_region(kwargs.get("region"))
    if resolved:
        params["region"] = resolved
    return params
```

#### 4.3 手动传递的方法

对于手动处理 region 的方法（`ocr_wait`、`ocr_assert`、`ocr_get_text`、`ocr_get_position`、`ocr_click_same_row_*`、`ocr_check_same_row_*`），统一使用 `_resolve_region`。

### 5. 使用示例

#### 5.1 AW 中使用

```python
# aw/web/meeting_aw.py
class MeetingAW(BaseAW):
    PLATFORM = "web"
    
    def should_layout_2x2_correct(self):
        """验证 2x2 布局是否正确。"""
        # 使用区域名称
        assert self.ocr_exist("主持人", region="meeting_main_2x2")
        assert self.ocr_exist("参会者A", region="meeting_sub1_2x2")
        
        # 不传 region = 全屏查找（原有行为不变）
        assert self.ocr_exist("会议标题")
        
        # 也支持直接传坐标
        assert self.ocr_exist("按钮", region=[100, 200, 300, 400])
```

#### 5.2 测试用例中使用

```python
# testcases/web/meeting/test_layout_001.py
@pytest.mark.users({"userA": "web"})
class TestClass:
    def test_layout_2x2_001(self, users):
        userA = users["userA"]
        userA.do_join_meeting()
        userA.should_layout_2x2_correct()
```

#### 5.3 添加新区域

只需编辑对应平台的 yaml 文件，无需修改代码：

```yaml
# config/regions/web.yaml（追加）
meeting_new_layout: [100, 100, 500, 500]
```

### 6. 改动汇总

| 改动项 | 改动量 |
|--------|--------|
| 新增 `config/regions/*.yaml` | 每平台一个文件 |
| 新增 `common/region_manager.py` | 约 60 行 |
| 改动 `aw/base_aw.py` | 新增 `_resolve_region` + 修改参数构建器 |

### 7. 设计决策记录

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 区域使用方式 | 字符串名称自动查找 | 使用方便，不传区域时保持原有全屏行为 |
| 配置组织 | 每平台独立文件 | 结构清晰，便于维护 |
| 管理方式 | 全局单例管理器 | 入侵 base_aw.py 最少（仅 5 行），架构清晰 |
| 配置结构 | 扁平结构 | 最简洁，命名体现布局 |