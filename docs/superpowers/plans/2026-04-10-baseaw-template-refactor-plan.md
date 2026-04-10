# BaseAW 模板简化重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 BaseAW 从 1156 行压缩到约 600 行，保持完整类型提示和零破坏性变更。

**Architecture:** 提取参数构建函数（`_ocr_params`、`_image_params`、`_same_row_params`）和执行包装层（`_exec`、`_exec_bool`、`_exec_str`、`_exec_list`），将方法体从 15-20 行压缩到 2-3 行。

**Tech Stack:** Python 3.x，pytest，现有 testagent client API。

**Spec Document:** `docs/superpowers/specs/2026-04-10-baseaw-template-refactor-design.md`

---

## 文件结构

| 文件 | 变化 | 说明 |
|------|------|------|
| `aw/base_aw.py` | 重构 | 主要修改 |
| `aw/INDEX.md` | 更新 | 方法索引（无结构变化） |
| `tests/unit/test_baseaw_refactor.py` | 新增 | 单元测试 |

---

### Task 1: 添加参数构建器

**Files:**
- Modify: `aw/base_aw.py` (在 `_execute_with_log` 方法后添加)

- [ ] **Step 1: 添加 `_ocr_params` 方法**

在 `_execute_exist_check` 方法后，添加参数构建器方法：

```python
# ── 参数构建器 ─────────────────────────────────────────

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

- [ ] **Step 2: 验证参数构建器导入**

Run: `source .venv/bin/activate && python -c "from aw.base_aw import BaseAW; print('_ocr_params:', hasattr(BaseAW, '_ocr_params'))"`
Expected: `_ocr_params: True`

- [ ] **Step 3: Commit**

```bash
git add aw/base_aw.py
git commit -m "refactor(baseaw): 添加参数构建器 _ocr_params, _image_params, _same_row_params"
```

---

### Task 2: 添加执行包装层

**Files:**
- Modify: `aw/base_aw.py` (在参数构建器后添加)

- [ ] **Step 1: 添加 `_exec` 系列方法**

在 `_same_row_params` 方法后添加：

```python
# ── 执行包装层 ─────────────────────────────────────────

def _exec(
    self,
    action_type: str,
    action_data: dict,
    log_args: dict,
    **extra,
) -> dict:
    """执行 action 并记录日志，失败时抛 AWError。

    Args:
        action_type: 动作类型，如 "ocr_click"
        action_data: 发给 worker 的完整 action dict
        log_args: 用于日志记录的参数
        extra: 可选的 result_extractor、image_path 等
    """
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

- [ ] **Step 2: 验证执行包装层导入**

Run: `source .venv/bin/activate && python -c "from aw.base_aw import BaseAW; methods = ['_exec', '_exec_bool', '_exec_str', '_exec_list']; for m in methods: print(f'{m}: {hasattr(BaseAW, m)}')"`
Expected: 所有方法返回 True

- [ ] **Step 3: Commit**

```bash
git add aw/base_aw.py
git commit -m "refactor(baseaw): 添加执行包装层 _exec, _exec_bool, _exec_str, _exec_list"
```

---

### Task 3: 重构 OCR 类方法

**Files:**
- Modify: `aw/base_aw.py` (OCR 方法区域，约 line 264-426)

- [ ] **Step 1: 重构 `ocr_click`**

将原方法替换为：

```python
def ocr_click(self, text: str, **kwargs) -> dict:
    """OCR 识别并点击。

    Args:
        text: 要识别并点击的文字。
        timeout: 超时时间（秒），默认 5。
        index: 选择第几个匹配结果（从 0 开始）。
        offset: 点击偏移量 {"x": 0, "y": 0}。
    """
    return self._exec("ocr_click",
        {"value": text, **self._ocr_params(kwargs)},
        {"text": text, **kwargs})
```

- [ ] **Step 2: 重构 `ocr_input`**

将原方法替换为：

```python
def ocr_input(self, label: str, content: str, **kwargs) -> dict:
    """OCR 定位后输入。

    Args:
        label: 要定位的文字标签。
        content: 要输入的内容。
        timeout: 超时时间（秒），默认 5。
        index: 选择第几个匹配结果（从 0 开始）。
        offset: 输入偏移量 {"x": 0, "y": 0}。
    """
    return self._exec("ocr_input",
        {"value": label, "text": content, **self._ocr_params(kwargs)},
        {"label": label, "content": content, **kwargs})
```

- [ ] **Step 3: 重构 `ocr_wait`**

将原方法替换为：

```python
def ocr_wait(self, text: str, **kwargs) -> dict:
    """等待文字出现。

    Args:
        text: 要等待的文字。
        timeout: 超时时间（秒），默认 5。
    """
    return self._exec("ocr_wait",
        {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
        {"text": text, **kwargs})
```

- [ ] **Step 4: 重构 `ocr_assert`**

将原方法替换为：

```python
def ocr_assert(self, text: str, **kwargs) -> dict:
    """断言文字存在。

    Args:
        text: 要断言的文字。
        timeout: 超时时间（秒），默认 5。
    """
    return self._exec("ocr_assert",
        {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
        {"text": text, **kwargs})
```

- [ ] **Step 5: 重构 `ocr_get_text`**

将原方法替换为：

```python
def ocr_get_text(self, **kwargs) -> str:
    """获取屏幕所有文字。

    Returns:
        识别到的文字内容。
    """
    return self._exec_str("ocr_get_text",
        {"value": "", "timeout": kwargs.get("timeout", 5) * 1000},
        {**kwargs})
```

- [ ] **Step 6: 重构 `ocr_paste`**

将原方法替换为：

```python
def ocr_paste(self, text: str, content: str, **kwargs) -> dict:
    """OCR 定位后粘贴剪贴板内容。

    Args:
        text: 要定位的文字。
        content: 剪贴板内容。
        timeout: 超时时间（秒），默认 5。
    """
    return self._exec("ocr_paste",
        {"value": text, "text": content, **self._ocr_params(kwargs)},
        {"text": text, "content": content, **kwargs})
```

- [ ] **Step 7: 重构 `ocr_move`**

将原方法替换为：

```python
def ocr_move(self, text: str, **kwargs) -> dict:
    """OCR 定位后移动鼠标（仅桌面端支持）。

    Args:
        text: 要定位的文字。
        timeout: 超时时间（秒），默认 5。
    """
    return self._exec("ocr_move",
        {"value": text, **self._ocr_params(kwargs)},
        {"text": text, **kwargs})
```

- [ ] **Step 8: 重构 `ocr_double_click`**

将原方法替换为：

```python
def ocr_double_click(self, text: str, **kwargs) -> dict:
    """OCR 定位后双击。

    Args:
        text: 要识别并双击的文字。
        timeout: 超时时间（秒），默认 5。
        index: 选择第几个匹配结果（从 0 开始）。
        offset: 点击偏移量 {"x": 0, "y": 0}。
    """
    return self._exec("ocr_double_click",
        {"value": text, **self._ocr_params(kwargs)},
        {"text": text, **kwargs})
```

- [ ] **Step 9: 重构 `ocr_exist`**

将原方法替换为：

```python
def ocr_exist(self, text: str, **kwargs) -> bool:
    """检查文字是否存在。

    Args:
        text: 要检查的文字。支持 `reg_` 前缀正则匹配，如 `reg_\\d+`。
        timeout: 超时时间（秒），默认 5。
        index: 选择第几个匹配结果（从 0 开始）。

    Returns:
        True 如果文字存在，False 如果不存在。不抛异常。
    """
    return self._exec_bool("ocr_exist",
        {"value": text, **self._ocr_params(kwargs)},
        {"text": text, **kwargs})
```

- [ ] **Step 10: 重构 `ocr_get_position`**

将原方法替换为：

```python
def ocr_get_position(self, text: str, **kwargs) -> list:
    """获取文字坐标列表。

    Args:
        text: 要查找的文字内容。支持 `reg_` 前缀正则匹配。
        timeout: 超时时间（秒），默认 5。

    Returns:
        坐标列表 [[x1, y1], [x2, y2], ...]。
    """
    return self._exec_list("ocr_get_position",
        {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
        {"text": text, **kwargs})
```

- [ ] **Step 11: 重构 `ocr_click_same_row_text`**

将原方法替换为：

```python
def ocr_click_same_row_text(self, anchor_text: str, target_text: str, **kwargs) -> dict:
    """点击锚点文本同一行的目标文本。

    Args:
        anchor_text: 锚点文本内容。
        target_text: 目标文本内容。
        anchor_index: 锚点文本索引（从 0 开始），默认 0。
        target_index: 目标文本索引（从 0 开始），默认 0。
        row_tolerance: 水平带范围（像素），默认 20。
        timeout: 超时时间（秒），默认 5。
        offset: 点击偏移量 {"x": 0, "y": 0}。
    """
    return self._exec("ocr_click_same_row_text",
        {"anchor_text": anchor_text, "value": target_text,
         **self._ocr_params(kwargs), **self._same_row_params(kwargs)},
        {"anchor_text": anchor_text, "target_text": target_text, **kwargs})
```

- [ ] **Step 12: 重构 `ocr_click_same_row_image`**

将原方法替换为：

```python
def ocr_click_same_row_image(self, anchor_text: str, image_path: str, **kwargs) -> dict:
    """点击锚点文本同一行的目标图片。

    Args:
        anchor_text: 锚点文本内容。
        image_path: 目标图片路径。
        anchor_index: 锚点文本索引（从 0 开始），默认 0。
        target_index: 目标图片索引（从 0 开始），默认 0。
        row_tolerance: 水平带范围（像素），默认 20。
        confidence: 匹置信度（0-1），默认 0.8。
        timeout: 超时时间（秒），默认 5。
        offset: 点击偏移量 {"x": 0, "y": 0}。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("ocr_click_same_row_image",
        {"anchor_text": anchor_text, "image_base64": image_base64,
         **self._ocr_params(kwargs), **self._same_row_params(kwargs),
         "threshold": kwargs.get("confidence", 0.8)},
        {"anchor_text": anchor_text, "image_path": image_path, **kwargs})
```

- [ ] **Step 13: 重构 `ocr_check_same_row_text`**

将原方法替换为：

```python
def ocr_check_same_row_text(self, anchor_text: str, target_text: str, **kwargs) -> dict:
    """检查锚点文本同一行的目标文本是否存在。

    Args:
        anchor_text: 锚点文本内容。
        target_text: 目标文本内容。
        anchor_index: 锚点文本索引（从 0 开始），默认 0。
        target_index: 目标文本索引（从 0 开始），默认 0。
        row_tolerance: 水平带范围（像素），默认 20。
        timeout: 超时时间（秒），默认 5。
    """
    return self._exec("ocr_check_same_row_text",
        {"anchor_text": anchor_text, "value": target_text,
         "timeout": kwargs.get("timeout", 5) * 1000, **self._same_row_params(kwargs)},
        {"anchor_text": anchor_text, "target_text": target_text, **kwargs})
```

- [ ] **Step 14: 重构 `ocr_check_same_row_image`**

将原方法替换为：

```python
def ocr_check_same_row_image(self, anchor_text: str, image_path: str, **kwargs) -> dict:
    """检查锚点文本同一行的目标图片是否存在。

    Args:
        anchor_text: 锚点文本内容。
        image_path: 目标图片路径。
        anchor_index: 锚点文本索引（从 0 开始），默认 0。
        target_index: 目标图片索引（从 0 开始），默认 0。
        row_tolerance: 水平带范围（像素），默认 20。
        confidence: 匹置信度（0-1），默认 0.8。
        timeout: 超时时间（秒），默认 5。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("ocr_check_same_row_image",
        {"anchor_text": anchor_text, "image_base64": image_base64,
         "timeout": kwargs.get("timeout", 5) * 1000, **self._same_row_params(kwargs),
         "threshold": kwargs.get("confidence", 0.8)},
        {"anchor_text": anchor_text, "image_path": image_path, **kwargs})
```

- [ ] **Step 15: 验证 OCR 方法导入**

Run: `source .venv/bin/activate && python -c "from aw.base_aw import BaseAW; methods = ['ocr_click', 'ocr_input', 'ocr_wait', 'ocr_assert', 'ocr_get_text', 'ocr_paste', 'ocr_move', 'ocr_double_click', 'ocr_exist', 'ocr_get_position', 'ocr_click_same_row_text', 'ocr_click_same_row_image', 'ocr_check_same_row_text', 'ocr_check_same_row_image']; for m in methods: print(f'{m}: {hasattr(BaseAW, m)}')"`
Expected: 所有方法返回 True

- [ ] **Step 16: Commit OCR 重构**

```bash
git add aw/base_aw.py
git commit -m "refactor(baseaw): 重构 OCR 类方法使用模板简化"
```

---

### Task 4: 重构 Image 类方法

**Files:**
- Modify: `aw/base_aw.py` (Image 方法区域，约 line 691-851)

- [ ] **Step 1: 重构 `image_click`**

将原方法替换为：

```python
def image_click(self, image_path: str, **kwargs) -> dict:
    """图像识别点击。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_click",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 2: 重构 `image_wait`**

将原方法替换为：

```python
def image_wait(self, image_path: str, **kwargs) -> dict:
    """等待图像出现。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_wait",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 3: 重构 `image_assert`**

将原方法替换为：

```python
def image_assert(self, image_path: str, **kwargs) -> dict:
    """断言图像存在。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_assert",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 4: 重构 `image_click_near_text`**

将原方法替换为：

```python
def image_click_near_text(self, image_path: str, text: str, **kwargs) -> dict:
    """点击文本附近最近的图像。

    Args:
        image_path: 图片路径。
        text: 文本内容。
        max_distance: 最大搜索距离（像素），默认 500。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_click_near_text",
        {"image_base64": image_base64, "value": text,
         "end_x": kwargs.get("max_distance", 500), **self._image_params(kwargs)},
        {"image_path": image_path, "text": text, **kwargs})
```

- [ ] **Step 5: 重构 `image_move`**

将原方法替换为：

```python
def image_move(self, image_path: str, **kwargs) -> dict:
    """图像识别后移动鼠标（仅桌面端支持）。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_move",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 6: 重构 `image_double_click`**

将原方法替换为：

```python
def image_double_click(self, image_path: str, **kwargs) -> dict:
    """图像识别后双击。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
        index: 选择第几个匹配结果（从 0 开始）。
        offset: 点击偏移量 {"x": 0, "y": 0}。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("image_double_click",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 7: 重构 `image_exist`**

将原方法替换为：

```python
def image_exist(self, image_path: str, **kwargs) -> bool:
    """检查图像是否存在。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。
        index: 选择第几个匹配结果（从 0 开始）。

    Returns:
        True 如果图像存在，False 如果不存在。不抛异常。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec_bool("image_exist",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 8: 重构 `image_get_position`**

将原方法替换为：

```python
def image_get_position(self, image_path: str, **kwargs) -> list:
    """获取图像坐标列表。

    Args:
        image_path: 图片路径。
        timeout: 超时时间（秒），默认 5。
        confidence: 匹置信度（0-1），默认 0.8。

    Returns:
        坐标列表 [[x1, y1], [x2, y2], ...]。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec_list("image_get_position",
        {"image_base64": image_base64, **self._image_params(kwargs)},
        {"image_path": image_path, **kwargs})
```

- [ ] **Step 9: 验证 Image 方法导入**

Run: `source .venv/bin/activate && python -c "from aw.base_aw import BaseAW; methods = ['image_click', 'image_wait', 'image_assert', 'image_click_near_text', 'image_move', 'image_double_click', 'image_exist', 'image_get_position']; for m in methods: print(f'{m}: {hasattr(BaseAW, m)}')"`
Expected: 所有方法返回 True

- [ ] **Step 10: Commit Image 重构**

```bash
git add aw/base_aw.py
git commit -m "refactor(baseaw): 重构 Image 类方法使用模板简化"
```

---

### Task 5: 重构坐标类方法

**Files:**
- Modify: `aw/base_aw.py` (坐标方法区域，约 line 853-936)

- [ ] **Step 1: 重构 `click`**

将原方法替换为：

```python
def click(self, x: int, y: int) -> dict:
    """坐标点击。

    Args:
        x: X 坐标。
        y: Y 坐标。
    """
    return self._exec("click", {"x": x, "y": y}, {"x": x, "y": y})
```

- [ ] **Step 2: 重构 `double_click`**

将原方法替换为：

```python
def double_click(self, x: int, y: int, **kwargs) -> dict:
    """坐标双击。

    Args:
        x: X 坐标。
        y: Y 坐标。
        offset: 点击偏移量 {"x": 0, "y": 0}。
    """
    action_data = {"x": x, "y": y}
    if "offset" in kwargs:
        action_data["offset"] = kwargs["offset"]
    return self._exec("double_click", action_data, {"x": x, "y": y, **kwargs})
```

- [ ] **Step 3: 重构 `move`**

将原方法替换为：

```python
def move(self, x: int, y: int, **kwargs) -> dict:
    """移动鼠标到指定坐标（仅桌面端支持）。

    Args:
        x: X 坐标。
        y: Y 坐标。
    """
    action_data = {"x": x, "y": y}
    if "offset" in kwargs:
        action_data["offset"] = kwargs["offset"]
    return self._exec("move", action_data, {"x": x, "y": y, **kwargs})
```

- [ ] **Step 4: 重构 `swipe`**

将原方法替换为：

```python
def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
    """滑动操作。

    Args:
        from_x: 起点 X 坐标。
        from_y: 起点 Y 坐标。
        to_x: 终点 X 坐标。
        to_y: 终点 Y 坐标。
        duration: 滑动持续时间（毫秒）。
    """
    action_data = {"from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}
    if "duration" in kwargs:
        action_data["duration"] = kwargs["duration"]
    return self._exec("swipe", action_data,
        {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y, **kwargs})
```

- [ ] **Step 5: 重构 `input_text`**

将原方法替换为：

```python
def input_text(self, x: int, y: int, text: str) -> dict:
    """在指定坐标输入文本。

    Args:
        x: X 坐标。
        y: Y 坐标。
        text: 要输入的文本。
    """
    return self._exec("input", {"x": x, "y": y, "text": text}, {"x": x, "y": y, "text": text})
```

- [ ] **Step 6: 验证坐标方法导入**

Run: `source .venv/bin/activate && python -c "from aw.base_aw import BaseAW; methods = ['click', 'double_click', 'move', 'swipe', 'input_text']; for m in methods: print(f'{m}: {hasattr(BaseAW, m)}')"`
Expected: 所有方法返回 True

- [ ] **Step 7: Commit 坐标重构**

```bash
git add aw/base_aw.py
git commit -m "refactor(baseaw): 重构坐标类方法使用模板简化"
```

---

### Task 6: 重构其他方法

**Files:**
- Modify: `aw/base_aw.py` (其他方法区域，约 line 1006-1156)

**方法清单（11个）**：`press`, `wait`, `start_app`, `stop_app`, `navigate`, `switched_page`, `close_page`, `web_image_upload`, `cmd_exec`, `screenshot`

- [ ] **Step 1: 重构 `press`**

将原方法替换为：

```python
def press(self, key: str) -> dict:
    """按键操作。

    Args:
        key: 按键名称（如 "Enter", "Tab", "Escape"）。
    """
    return self._exec("press", {"key": key}, {"key": key})
```

- [ ] **Step 2: 重构 `wait`**

将原方法替换为：

```python
def wait(self, duration: float) -> dict:
    """固定等待。

    Args:
        duration: 等待时间（秒），与 time.sleep() 单位一致。
    """
    duration_ms = int(duration * 1000)
    return self._exec("wait", {"value": str(duration_ms)}, {"duration_ms": duration_ms})
```

- [ ] **Step 3: 重构 `start_app`**

将原方法替换为：

```python
def start_app(self, app_id: str) -> dict:
    """启动应用。

    Args:
        app_id: 应用 ID 或名称。
    """
    return self._exec("start_app", {"value": app_id}, {"app_id": app_id})
```

- [ ] **Step 4: 重构 `stop_app`**

将原方法替换为：

```python
def stop_app(self, app_id: str) -> dict:
    """关闭应用。

    Args:
        app_id: 应用 ID 或名称。
    """
    return self._exec("stop_app", {"value": app_id}, {"app_id": app_id})
```

- [ ] **Step 5: 重构 `navigate`**

将原方法替换为：

```python
def navigate(self, url: str) -> dict:
    """导航到 URL（Web 端专用）。

    Args:
        url: 目标 URL。
    """
    return self._exec("navigate", {"value": url}, {"url": url})
```

- [ ] **Step 6: 重构 `switched_page`**

将原方法替换为：

```python
def switched_page(self, page_index: int) -> dict:
    """切换到指定页面（Web 端专用）。

    Args:
        page_index: 页面索引（从 1 开始），如 1 表示第一个打开的标签页。
    """
    return self._exec("switched_page", {"value": str(page_index)}, {"page_index": page_index})
```

- [ ] **Step 7: 重构 `close_page`**

将原方法替换为：

```python
def close_page(self) -> dict:
    """关闭当前页面（Web 端专用）。

    关闭后会自动切换到浏览器当前显示的页面。
    """
    return self._exec("close_page", {}, {})
```

- [ ] **Step 8: 重构 `web_image_upload`**

将原方法替换为：

```python
def web_image_upload(self, x: int, y: int, image_path: str) -> dict:
    """处理文件上传弹窗（Web 端专用）。

    使用 Playwright 文件选择器 API 处理原生文件上传对话框。

    Args:
        x: 点击位置的 X 坐标。
        y: 点击位置的 Y 坐标。
        image_path: 要上传的图片路径。
    """
    image_base64 = self._load_image_as_base64(image_path)
    if not image_base64:
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return self._exec("web_image_upload",
        {"x": x, "y": y, "image_base64": image_base64},
        {"x": x, "y": y, "image_path": image_path})
```

- [ ] **Step 9: 重构 `cmd_exec`**

将原方法替换为：

```python
def cmd_exec(self, command: str, **kwargs) -> dict:
    """在宿主机执行命令。

    Args:
        command: 要执行的命令字符串。
        timeout: 超时时间（秒），默认 30。
    """
    timeout_ms = kwargs.get("timeout", 30) * 1000
    return self._exec("cmd_exec",
        {"value": command, "timeout": timeout_ms},
        {"command": command, **kwargs})
```

- [ ] **Step 10: `screenshot` 保持不变**

`screenshot` 方法有特殊逻辑（直接调用 `client.execute`，不经过 `_execute_with_log`），保持不变。

- [ ] **Step 11: 验证其他方法导入**

Run: `source .venv/bin/activate && python -c "from aw.base_aw import BaseAW; methods = ['press', 'wait', 'start_app', 'stop_app', 'navigate', 'switched_page', 'close_page', 'web_image_upload', 'cmd_exec', 'screenshot']; for m in methods: print(f'{m}: {hasattr(BaseAW, m)}')"`
Expected: 所有方法返回 True

- [ ] **Step 12: Commit 其他方法重构**

```bash
git add aw/base_aw.py
git commit -m "refactor(baseaw): 重构其他方法使用模板简化"
```

---

### Task 7: 更新 INDEX.md

**Files:**
- Modify: `aw/INDEX.md`

- [ ] **Step 1: 更新 INDEX.md 方法索引**

确认方法索引表已包含所有方法（之前已更新，检查是否完整）。

Run: `cat aw/INDEX.md | grep -E "^\| \`" | wc -l`
Expected: 约 35+ 行（方法数量）

- [ ] **Step 2: Commit INDEX.md**

```bash
git add aw/INDEX.md
git commit -m "docs: 更新 INDEX.md 方法索引"
```

---

### Task 8: 验证重构结果

**Files:**
- Check: `aw/base_aw.py`

- [ ] **Step 1: 检查代码行数**

Run: `wc -l aw/base_aw.py`
Expected: 约 600-700 行（相比原来 1156 行减少约 50%）

- [ ] **Step 2: 运行现有测试用例**

Run: `source .venv/bin/activate && pytest testcases/ -v --tb=short -x 2>&1 | head -50`
Expected: 现有测试用例正常运行（如果有测试）

- [ ] **Step 3: 验证方法签名一致**

Run: `source .venv/bin/activate && python -c "
from aw.base_aw import BaseAW
import inspect

# 检查关键方法的签名
methods_to_check = ['ocr_click', 'image_click', 'click', 'navigate', 'ocr_exist']
for m in methods_to_check:
    method = getattr(BaseAW, m)
    sig = inspect.signature(method)
    print(f'{m}: {sig}')
"`
Expected: 方法签名保持不变

- [ ] **Step 4: Commit 最终验证**

```bash
git status
git add -A
git commit -m "refactor(baseaw): 完成模板简化重构，代码量减少约50%"
```

---

### Task 9: 清理和总结

- [ ] **Step 1: 检查 git log**

Run: `git log --oneline -10`
Expected: 看到 5+ 个 refactor commit

- [ ] **Step 2: 检查代码差异统计**

Run: `git diff HEAD~5 --stat aw/base_aw.py`
Expected: 显示代码变化统计

- [ ] **Step 3: 推送变更（可选）**

如果需要推送：
```bash
git push origin main
```

---

## 执行摘要

| Task | 说明 | 预计耗时 |
|------|------|----------|
| Task 1 | 添加参数构建器 | 5 min |
| Task 2 | 添加执行包装层 | 5 min |
| Task 3 | 重构 OCR 类方法 (14个) | 15 min |
| Task 4 | 重构 Image 类方法 (8个) | 10 min |
| Task 5 | 重构坐标类方法 (5个) | 5 min |
| Task 6 | 重构其他方法 (11个) | 10 min |
| Task 7 | 更新 INDEX.md | 2 min |
| Task 8 | 验证重构结果 | 5 min |
| Task 9 | 清理和总结 | 2 min |

**总计**: 约 60 分钟

---

## 风险检查点

| 检查点 | 方法 |
|--------|------|
| 参数构建器覆盖完整性 | 对照 api.yaml 检查 timeout/index/offset 等 |
| exist 方法返回 bool | `_exec_bool` 不抛异常 |
| get_text/get_position 返回正确类型 | `_exec_str`/`_exec_list` |
| image 方法图片加载 | 保持 `FileNotFoundError` 检查 |
| screenshot 保持特殊逻辑 | 不使用 `_exec` |