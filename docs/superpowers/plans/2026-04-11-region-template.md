# 布局区域模板系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现布局区域模板系统，支持按名称引用区域坐标，不同平台配置独立。

**Architecture:** 单例 RegionManager 管理各平台配置，BaseAW 新增 `_resolve_region` 方法将字符串名称解析为坐标数组。

**Tech Stack:** Python, yaml, pytest

**设计文档:** [设计文档](../specs/2026-04-11-region-template-design.md)

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `config/regions/web.yaml` | Web 平台区域配置 |
| `config/regions/windows.yaml` | Windows 平台区域配置 |
| `config/regions/android.yaml` | Android 平台区域配置 |
| `config/regions/ios.yaml` | iOS 平台区域配置 |
| `config/regions/mac.yaml` | Mac 平台区域配置 |
| `common/region_manager.py` | 区域配置管理器（单例） |
| `testcases/common/test_region_manager.py` | RegionManager 单元测试 |
| `aw/base_aw.py` | 新增 `_resolve_region` 方法，修改参数构建器 |

---

## Task 1: 创建测试文件（TDD）

**Files:**
- Create: `testcases/common/__init__.py`
- Create: `testcases/common/test_region_manager.py`

- [ ] **Step 1: 创建测试目录和 __init__.py**

```bash
mkdir -p testcases/common
touch testcases/common/__init__.py
```

- [ ] **Step 2: 编写 RegionManager 单元测试**

```python
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
```

- [ ] **Step 3: 运行测试验证失败**

```bash
source .venv/bin/activate
pytest testcases/common/test_region_manager.py -v
```
Expected: 导入失败，提示 ModuleNotFoundError: No module named 'common.region_manager'

- [ ] **Step 4: 提交测试文件**

```bash
git add testcases/common/
git commit -m "test: 添加 RegionManager 单元测试"
```

---

## Task 2: 创建 RegionManager 实现

**Files:**
- Create: `common/region_manager.py`

- [ ] **Step 1: 编写 RegionManager 实现**

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
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # 扁平结构，直接存储，验证坐标格式
        RegionManager._configs[platform] = {
            name: coords for name, coords in data.items()
            if isinstance(coords, list) and len(coords) == 4
            and all(isinstance(c, int) for c in coords)
        }
    
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
```

- [ ] **Step 2: 运行语法检查**

```bash
source .venv/bin/activate
python -m py_compile common/region_manager.py && echo "语法检查通过"
```
Expected: "语法检查通过"

- [ ] **Step 3: 运行测试（会因缺少配置文件部分失败）**

```bash
source .venv/bin/activate
pytest testcases/common/test_region_manager.py -v
```
Expected: 部分 PASS（单例测试），部分 FAIL（缺少配置文件）

- [ ] **Step 4: 提交 RegionManager**

```bash
git add common/region_manager.py
git commit -m "feat: 添加 RegionManager 区域配置管理器"
```

---

## Task 3: 创建区域配置文件

**Files:**
- Create: `config/regions/web.yaml`
- Create: `config/regions/windows.yaml`
- Create: `config/regions/android.yaml`
- Create: `config/regions/ios.yaml`
- Create: `config/regions/mac.yaml`

- [ ] **Step 1: 创建配置目录**

```bash
mkdir -p config/regions
```

- [ ] **Step 2: 创建 Web 平台配置**

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

- [ ] **Step 3: 创建 Windows 平台配置**

```yaml
# config/regions/windows.yaml
meeting_main_2x2: [0, 0, 960, 540]
meeting_gallery: [0, 0, 1920, 1080]
```

- [ ] **Step 4: 创建 Android 平台配置**

```yaml
# config/regions/android.yaml
meeting_main_2x2: [0, 0, 480, 270]
meeting_gallery: [0, 0, 1080, 1920]
```

- [ ] **Step 5: 创建 iOS 平台配置**

```yaml
# config/regions/ios.yaml
meeting_main_2x2: [0, 0, 390, 422]
meeting_gallery: [0, 0, 1170, 2532]
```

- [ ] **Step 6: 创建 Mac 平台配置**

```yaml
# config/regions/mac.yaml
meeting_main_2x2: [0, 0, 960, 540]
meeting_gallery: [0, 0, 1920, 1080]
```

- [ ] **Step 7: 运行 RegionManager 测试验证通过**

```bash
source .venv/bin/activate
pytest testcases/common/test_region_manager.py -v
```
Expected: All PASS

- [ ] **Step 8: 提交配置文件**

```bash
git add config/regions/
git commit -m "feat: 添加各平台区域配置文件"
```

---

## Task 4: 修改 BaseAW 添加 _resolve_region

**Files:**
- Modify: `aw/base_aw.py` (第 671 行后添加方法)

### 4.1 添加 _resolve_region 方法

- [ ] **Step 1: 在 BaseAW 类中添加 _resolve_region 方法**

位置：在 `# ── 参数构建器 ─────────────────────────────────────────` 注释行（约第 671 行）之后添加

```python
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

- [ ] **Step 2: 运行语法检查**

```bash
source .venv/bin/activate
python -m py_compile aw/base_aw.py && echo "语法检查通过"
```
Expected: "语法检查通过"

### 4.2 修改 _ocr_params (第 673-686 行)

- [ ] **Step 3: 修改 _ocr_params 使用 _resolve_region**

将原来第 684-685 行的：
```python
if "region" in kwargs:
    params["region"] = kwargs["region"]
```
改为：
```python
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    params["region"] = resolved
```

### 4.3 修改 _image_params (第 688-703 行)

- [ ] **Step 4: 修改 _image_params 使用 _resolve_region**

将原来第 701-702 行的：
```python
if "region" in kwargs:
    params["region"] = kwargs["region"]
```
改为：
```python
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    params["region"] = resolved
```

- [ ] **Step 5: 运行语法检查**

```bash
source .venv/bin/activate
python -m py_compile aw/base_aw.py && echo "语法检查通过"
```
Expected: "语法检查通过"

### 4.4 修改手动处理 region 的方法

所有修改统一使用以下模式：将 `if "region" in kwargs: action_data["region"] = kwargs["region"]` 改为使用 `_resolve_region`。

- [ ] **Step 6: 修改 ocr_wait**

查找代码：
```python
action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
if "region" in kwargs:
    action_data["region"] = kwargs["region"]
```
改为：
```python
action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
```

- [ ] **Step 7: 修改 ocr_assert**

查找代码：
```python
action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
if "region" in kwargs:
    action_data["region"] = kwargs["region"]
```
改为：
```python
action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
```

- [ ] **Step 8: 修改 ocr_get_text**

查找代码：
```python
action_data = {"value": "", "timeout": kwargs.get("timeout", 5) * 1000}
if "region" in kwargs:
    action_data["region"] = kwargs["region"]
```
改为：
```python
action_data = {"value": "", "timeout": kwargs.get("timeout", 5) * 1000}
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
```

- [ ] **Step 9: 修改 ocr_get_position**

查找代码：
```python
action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
if "region" in kwargs:
    action_data["region"] = kwargs["region"]
```
改为：
```python
action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
```

- [ ] **Step 10: 修改 ocr_click_same_row_text**

查找代码：
```python
if "region" in kwargs:
    action_data["region"] = kwargs["region"]
```
在 offset 处理之后添加：
```python
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
```

- [ ] **Step 11: 修改 ocr_click_same_row_image**

查找代码：
```python
if "offset" in kwargs:
    action_data["offset"] = kwargs["offset"]
if "region" in kwargs:
    action_data["region"] = kwargs["region"]
```
改为：
```python
if "offset" in kwargs:
    action_data["offset"] = kwargs["offset"]
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
```

- [ ] **Step 12: 修改 ocr_check_same_row_text**

查找代码：
```python
return self._exec("ocr_check_same_row_text",
    {
        "anchor_text": anchor_text,
        "value": target_text,
        **self._same_row_params(kwargs),
        "timeout": kwargs.get("timeout", 5) * 1000,
    },
    {"anchor_text": anchor_text, "target_text": target_text, **kwargs})
```
改为先构建 action_data 再传参：
```python
action_data = {
    "anchor_text": anchor_text,
    "value": target_text,
    **self._same_row_params(kwargs),
    "timeout": kwargs.get("timeout", 5) * 1000,
}
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
return self._exec("ocr_check_same_row_text", action_data,
    {"anchor_text": anchor_text, "target_text": target_text, **kwargs})
```

- [ ] **Step 13: 修改 ocr_check_same_row_image**

查找代码：
```python
return self._exec("ocr_check_same_row_image",
    {
        "anchor_text": anchor_text,
        "image_base64": image_base64,
        **self._same_row_params(kwargs),
        "threshold": kwargs.get("confidence", 0.8),
        "timeout": kwargs.get("timeout", 5) * 1000,
        **({"region": kwargs["region"]} if "region" in kwargs else {}),
    },
    {"anchor_text": anchor_text, "image_path": image_path, **kwargs})
```
改为：
```python
action_data = {
    "anchor_text": anchor_text,
    "image_base64": image_base64,
    **self._same_row_params(kwargs),
    "threshold": kwargs.get("confidence", 0.8),
    "timeout": kwargs.get("timeout", 5) * 1000,
}
resolved = self._resolve_region(kwargs.get("region"))
if resolved:
    action_data["region"] = resolved
return self._exec("ocr_check_same_row_image", action_data,
    {"anchor_text": anchor_text, "image_path": image_path, **kwargs})
```

- [ ] **Step 14: 运行语法检查**

```bash
source .venv/bin/activate
python -m py_compile aw/base_aw.py && echo "语法检查通过"
```
Expected: "语法检查通过"

### 4.5 提交改动

- [ ] **Step 15: 提交 BaseAW 改动**

```bash
git add aw/base_aw.py
git commit -m "feat: BaseAW 添加 _resolve_region 方法，支持区域名称解析"
```

---

## Task 5: 更新 docstring

**Files:**
- Modify: `aw/base_aw.py`

- [ ] **Step 1: 更新相关方法的 docstring**

将 docstring 中 `region: 操作区域 [x1, y1, x2, y2]` 改为：
`region: 操作区域名称或 [x1, y1, x2, y2]。`

影响的方法：
- `ocr_click`
- `ocr_input`
- `ocr_wait`
- `ocr_assert`
- `ocr_get_text`
- `ocr_paste`
- `ocr_move`
- `ocr_double_click`
- `ocr_exist`
- `ocr_get_position`
- `ocr_click_same_row_text`
- `ocr_click_same_row_image`
- `ocr_check_same_row_text`
- `ocr_check_same_row_image`
- `image_click`
- `image_wait`
- `image_assert`
- `image_click_near_text`
- `image_move`
- `image_double_click`
- `image_exist`
- `image_get_position`

- [ ] **Step 2: 运行语法检查**

```bash
source .venv/bin/activate
python -m py_compile aw/base_aw.py && echo "语法检查通过"
```

- [ ] **Step 3: 提交 docstring 更新**

```bash
git add aw/base_aw.py
git commit -m "docs: 更新 region 参数说明，支持区域名称"
```

---

## Task 6: 更新 pytest 配置

**Files:**
- Modify: `pytest.ini`

- [ ] **Step 1: 添加 testcases/common 到 testpaths**

将 pytest.ini 的 testpaths 从：
```ini
testpaths = windows web mac ios android
```
改为（统一使用完整路径）：
```ini
testpaths = testcases/windows testcases/web testcases/mac testcases/ios testcases/android testcases/common
```

- [ ] **Step 2: 提交 pytest 配置更新**

```bash
git add pytest.ini
git commit -m "chore: 统一 pytest testpaths 格式，添加 testcases/common"
```

---

## Task 7: 最终验证

- [ ] **Step 1: 运行所有单元测试**

```bash
source .venv/bin/activate
pytest testcases/common/test_region_manager.py -v
```
Expected: All PASS

- [ ] **Step 2: 验证 BaseAW 导入正常**

```bash
source .venv/bin/activate
python -c "from aw.base_aw import BaseAW; print('导入成功')"
```
Expected: "导入成功"

- [ ] **Step 3: 验证 RegionManager 导入正常**

```bash
source .venv/bin/activate
python -c "from common.region_manager import RegionManager; rm = RegionManager.get_instance(); print(rm.list_regions('web'))"
```
Expected: 输出区域名称列表

---

## 验收标准

1. RegionManager 单例正确加载各平台配置
2. `_resolve_region` 正确解析字符串名称和坐标数组
3. 不传 region 时保持原有全屏行为
4. 所有语法检查通过
5. 单元测试全部通过