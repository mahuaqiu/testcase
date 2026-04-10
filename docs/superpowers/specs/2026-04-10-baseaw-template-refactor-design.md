# BaseAW 模板简化重构设计

## 背景

BaseAW 当前有 **1156 行代码**，包含 **37 个公共方法**。随着 testagent API 持续扩展（如近期新增 `switched_page`、`web_image_upload`、`ocr_get_position` 等），代码膨胀问题日益严重。

**问题本质**：
- 每个方法遵循高度重复的模式：构建 `action_data` dict → 调用 `_execute_with_log`
- 新增一个 action 需要写 15-20 行代码（包括 docstring、参数处理、调用核心方法）
- 参数处理逻辑（如 `timeout` 默认值转换、`offset` 可选处理）分散在各方法中

## 目标

- **减少代码量约 50%**：从 1156 行压缩到约 600 行
- **保持完整类型提示**：IDE autocompletion、参数校验保持原生体验
- **简化新增流程**：新增 action 只需写 2-3 行代码
- **零破坏性变更**：现有测试用例无需修改

## 设计方案

### 核心思路

提取**参数构建函数**和**核心执行包装器**，将方法体从 15-20 行压缩到 2-3 行。

### 架构概览

```
BaseAW (重构后 ~600 行)
├── 基础设施层 (~250行)
│   ├── __init__, __init_subclass__, _find_parent_aw
│   ├── _execute_with_log, _execute_exist_check      # 保持不变
│   ├── _ocr_params, _image_params, _same_row_params # 新增：参数构建器
│   └── _exec, _exec_bool, _exec_str, _exec_list     # 新增：执行包装层
│
├── OCR 方法层 (13个方法, ~100行)
│   └── 每个方法 2-4 行 + docstring
│
├── Image 方法层 (8个方法, ~80行)
│   └── 每个方法 3-4 行 + docstring (含图片加载检查)
│
├── 坐标方法层 (5个方法, ~20行)
│   └── 每个方法 2 行 + docstring
│
├── 其他方法层 (11个方法, ~60行)
│   └── 每个方法 2-3 行 + docstring
│
└── 特殊方法 (~30行)
│   ├── screenshot
│   └── _load_image_as_base64
```

### 详细设计

#### 1. 参数构建器

按 action 类别提取通用参数构建逻辑：

```python
class BaseAW:
    def _ocr_params(self, kwargs: dict) -> dict:
        """构建 OCR 类 action 的通用参数。

        包含：timeout(默认5秒转毫秒)、index、offset
        """
        params = {"timeout": kwargs.get("timeout", 5) * 1000}
        if "index" in kwargs:
            params["index"] = kwargs["index"]
        if "offset" in kwargs:
            params["offset"] = kwargs["offset"]
        return params

    def _image_params(self, kwargs: dict) -> dict:
        """构建 Image 类 action 的通用参数。

        包含：timeout、threshold(默认0.8)、index、offset
        """
        params = {
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),  # alias
        }
        if "index" in kwargs:
            params["index"] = kwargs["index"]
        if "offset" in kwargs:
            params["offset"] = kwargs["offset"]
        return params

    def _same_row_params(self, kwargs: dict) -> dict:
        """构建 same_row 类 action 的通用参数。

        包含：anchor_index、target_index、row_tolerance
        """
        return {
            "anchor_index": kwargs.get("anchor_index", 0),
            "target_index": kwargs.get("target_index", 0),
            "row_tolerance": kwargs.get("row_tolerance", 20),
        }
```

#### 2. 执行包装层

基于现有的 `_execute_with_log` 和 `_execute_exist_check`，提供便捷包装：

```python
class BaseAW:
    def _exec(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        **extra,
    ) -> dict:
        """执行 action 并记录日志，失败时抛 AWError。"""
        return self._execute_with_log(action_type, action_data, log_args, **extra)

    def _exec_bool(self, action_type: str, action_data: dict, log_args: dict) -> bool:
        """执行 exist 类 action，返回 bool，不抛异常。"""
        result = self._execute_exist_check(action_type, action_data, log_args)
        return result.get("exists", False)

    def _exec_str(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        field: str = "output"
    ) -> str:
        """执行 action 并提取 str 返回值。"""
        result = self._exec(action_type, action_data, log_args)
        if result.get("actions"):
            return result["actions"][0].get(field, "")
        return ""

    def _exec_list(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        key: str = "positions"
    ) -> list:
        """执行 action 并解析 list 返回值（如 positions）。"""
        import json
        result = self._exec(action_type, action_data, log_args)
        if result.get("actions"):
            output = result["actions"][0].get("output", "")
            if output:
                try:
                    return json.loads(output).get(key, [])
                except json.JSONDecodeError:
                    pass
        return []
```

#### 3. 方法模板示例

**OCR 类方法**：

```python
def ocr_click(self, text: str, **kwargs) -> dict:
    """OCR 识别并点击。"""
    return self._exec("ocr_click",
        {"value": text, **self._ocr_params(kwargs)},
        {"text": text, **kwargs})

def ocr_input(self, label: str, content: str, **kwargs) -> dict:
    """OCR 定位后输入。"""
    return self._exec("ocr_input",
        {"value": label, "text": content, **self._ocr_params(kwargs)},
        {"label": label, "content": content, **kwargs})

def ocr_exist(self, text: str, **kwargs) -> bool:
    """检查文字是否存在。"""
    return self._exec_bool("ocr_exist",
        {"value": text, "timeout": kwargs.get("timeout", 5) * 1000, "index": kwargs.get("index", 0)},
        {"text": text, **kwargs})

def ocr_get_position(self, text: str, **kwargs) -> list:
    """获取文字坐标列表。"""
    return self._exec_list("ocr_get_position",
        {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
        {"text": text, **kwargs})
```

**Image 类方法**：

```python
def image_click(self, image_path: str, **kwargs) -> dict:
    """图像识别点击。"""
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_click",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})

def image_exist(self, image_path: str, **kwargs) -> bool:
    """检查图像是否存在。"""
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec_bool("image_exist",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

**坐标类方法**：

```python
def click(self, x: int, y: int) -> dict:
    """坐标点击。"""
    return self._exec("click", {"x": x, "y": y}, {"x": x, "y": y})

def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
    """滑动操作。"""
    action_data = {"from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}
    if "duration" in kwargs:
        action_data["duration"] = kwargs["duration"]
    return self._exec("swipe", action_data, {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y, **kwargs})
```

**Web 专用方法**：

```python
def navigate(self, url: str) -> dict:
    """导航到 URL。"""
    return self._exec("navigate", {"value": url}, {"url": url})

def switched_page(self, page_index: int) -> dict:
    """切换到指定页面。"""
    return self._exec("switched_page", {"value": str(page_index)}, {"page_index": page_index})

def close_page(self) -> dict:
    """关闭当前页面。"""
    return self._exec("close_page", {}, {})

def web_image_upload(self, x: int, y: int, image_path: str) -> dict:
    """处理文件上传弹窗。"""
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("web_image_upload",
        {"x": x, "y": y, "image_base64": image_base64},
        {"x": x, "y": y, "image_path": image_path})
```

## 新增 Action 流程

当 testagent 新增 action 时，只需：

1. **确定 action 类别**：OCR、Image、坐标、或其他
2. **写 2-3 行方法**：
   ```python
   def new_action(self, param1: str, **kwargs) -> dict:
       """新动作说明。"""
       return self._exec("new_action",
           {"value": param1, **self._ocr_params(kwargs)},
           {"param1": param1, **kwargs})
   ```
3. **更新 INDEX.md**：添加方法到索引表

## 迁移策略

- **零破坏性变更**：所有公共方法签名保持不变
- **逐步迁移**：可分批迁移，先迁移简单方法（OCR 类），再迁移复杂方法
- **测试验证**：迁移后运行现有测试用例确保行为一致

## 影响范围

| 文件 | 变化 |
|------|------|
| `aw/base_aw.py` | 从 1156 行压缩到约 600 行 |
| `aw/INDEX.md` | 更新方法索引（无结构变化） |
| 测试用例 | 无变化（方法签名不变） |

## 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| 参数构建遗漏 | 低 | 对照 api.yaml 逐项检查 |
| 特殊返回类型处理遗漏 | 低 | exist/get_text/get_position 有专门包装器 |
| 并行执行兼容性 | 低 | `_execute_with_log` 保持不变，仍支持 parallel 上下文 |