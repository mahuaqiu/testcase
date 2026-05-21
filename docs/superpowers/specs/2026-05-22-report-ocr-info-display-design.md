---
title: 报告显示 OCR 信息
date: 2026-05-22
status: draft
---

# 报告显示 OCR 信息

## 背景

Worker 在执行 OCR 相关操作时，会返回 `ocr_info` 字段，包含当前屏幕识别到的所有文本及其坐标位置。目前报告只在失败时显示 OCR 信息，但成功的步骤也可能存在识别错误（比如识别到错误的位置或文字），需要查看 OCR 信息来定位问题。

## 目标

在 HTML 报告中显示所有 OCR 相关操作的 `ocr_info` 信息，帮助用户定位识别问题。

## 范围

### 需要显示 ocr_info 的方法

**OCR 方法（共 11 个）**：
- `ocr_click`
- `ocr_input`
- `ocr_wait`
- `ocr_assert`
- `ocr_find` / `ocr_exists`
- `ocr_get_text`
- `ocr_paste`
- `ocr_move`
- `ocr_double_click`
- `ocr_click_same_row_text`
- `ocr_check_same_row_text`

**OCR 相关 Image 方法（共 3 个）**：
- `image_click_near_text`
- `ocr_click_same_row_image`
- `ocr_check_same_row_image`

### 不需要显示 ocr_info 的方法

- 纯 Image 方法（`image_click`, `image_wait`, `image_assert`, `image_move`, `image_double_click`, `image_exist`）：图像匹配不依赖 OCR
- 其他所有非 OCR 相关方法

## 设计方案

### 判断逻辑

在 `_render_timeline_step` 方法中，根据方法名判断是否需要显示 OCR 信息：

```python
# 判断是否是 OCR 相关方法（需要显示 ocr_info）
OCR_METHODS = {
    # OCR 方法
    "ocr_click", "ocr_input", "ocr_wait", "ocr_assert", "ocr_find",
    "ocr_exists", "ocr_get_text", "ocr_paste", "ocr_move", "ocr_double_click",
    "ocr_click_same_row_text", "ocr_check_same_row_text",
    # OCR 相关 Image 方法
    "image_click_near_text", "ocr_click_same_row_image", "ocr_check_same_row_image",
}

def should_show_ocr_info(method: str) -> bool:
    """判断是否需要显示 OCR 信息。"""
    return method in OCR_METHODS
```

### 显示方式

**成功时**：
- OCR 信息显示在展开详情区域
- 默认折叠，需要点击步骤标题展开查看

**失败时**：
- OCR 信息显示在展开详情区域
- 默认展开，方便用户快速定位问题

### UI 样式

沿用现有的 OCR 信息样式（已在报告中实现）：

```html
<div class="step-ocr-box">
    <div class="step-ocr-label">OCR 识别结果</div>
    <div class="step-ocr-content">
        <span class="ocr-text-item">"文本内容" (x, y)</span>
        ...
    </div>
</div>
```

样式定义：
```css
.step-ocr-box { margin-bottom: 10px; }
.step-ocr-label { font-size: 11px; color: #6b7280; font-weight: 600; margin-bottom: 4px; }
.step-ocr-content {
    background: white;
    padding: 8px;
    border-radius: 6px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    color: #4b5563;
    line-height: 1.6;
}
.ocr-text-item {
    display: inline-block;
    margin: 3px 5px;
    padding: 3px 8px;
    background: #f3f4f6;
    border-radius: 4px;
}
```

## 实现细节

### 修改文件

`common/report_generator.py`

### 修改点

1. **添加 OCR 方法集合常量**：定义需要显示 ocr_info 的方法名集合

2. **修改 `_render_timeline_step` 方法**：
   - 在"OCR 信息"部分，修改判断逻辑：从"失败时显示"改为"OCR 相关方法时显示"
   - 成功时的 OCR 信息也添加到 `detail_parts` 中

### 代码修改位置

`_render_timeline_step` 方法中，第 232-248 行的 OCR 信息渲染逻辑：

**当前逻辑**：
```python
# OCR 信息（失败时有 OCR 数据时显示）
ocr_info = result.get("ocr_info", [])
if ocr_info and isinstance(ocr_info, list) and len(ocr_info) > 0:
    # 仅在失败时显示
    if not success:
        # 渲染 OCR 信息...
```

**修改后逻辑**：
```python
# OCR 信息（OCR 相关方法时显示）
ocr_info = result.get("ocr_info", [])
if ocr_info and isinstance(ocr_info, list) and len(ocr_info) > 0:
    # 判断是否是 OCR 相关方法
    if should_show_ocr_info(method):
        # 渲染 OCR 信息（成功和失败都显示）
        # ...
```

## 测试验证

1. 运行包含 OCR 操作的测试用例
2. 检查生成的 HTML 报告：
   - OCR 方法成功时：能看到 OCR 信息（折叠状态）
   - OCR 方法失败时：能看到 OCR 信息（展开状态）
   - 非 OCR 方法：不显示 OCR 信息

## 影响范围

- 仅影响报告显示逻辑，不影响测试执行
- 已有报告样式无需修改，沿用现有 OCR 信息样式