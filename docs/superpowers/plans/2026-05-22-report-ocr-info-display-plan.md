# 报告显示 OCR 信息 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 HTML 报告中显示所有 OCR 相关操作的 ocr_info 信息，用于定位识别问题

**Architecture:** 在 report_generator.py 中添加 OCR 方法集合判断，修改渲染逻辑使其在成功和失败时都显示 OCR 信息

**Tech Stack:** Python, HTML 报告生成

---

## 文件结构

**修改文件：**
- `common/report_generator.py` - 报告生成器，需要添加 OCR 方法判断逻辑和修改渲染逻辑

---

### Task 1: 添加 OCR 方法集合常量

**Files:**
- Modify: `common/report_generator.py:1-10` (在类定义前添加常量)

- [ ] **Step 1: 添加 OCR_METHODS 常量和判断函数**

在 `HTMLReportGenerator` 类定义前添加：

```python
# OCR 相关方法集合（需要显示 ocr_info）
OCR_METHODS = {
    # OCR 方法
    "ocr_click", "ocr_input", "ocr_wait", "ocr_assert", "ocr_find",
    "ocr_exists", "ocr_get_text", "ocr_paste", "ocr_move", "ocr_double_click",
    "ocr_click_same_row_text", "ocr_check_same_row_text",
    # OCR 相关 Image 方法
    "image_click_near_text", "ocr_click_same_row_image", "ocr_check_same_row_image",
}


def should_show_ocr_info(method: str) -> bool:
    """判断是否需要显示 OCR 信息。

    Args:
        method: 方法名。

    Returns:
        True 如果需要显示 OCR 信息。
    """
    return method in OCR_METHODS
```

- [ ] **Step 2: 验证代码语法正确**

运行: `python -m py_compile common/report_generator.py`
预期: 无错误输出

---

### Task 2: 修改 OCR 信息渲染逻辑

**Files:**
- Modify: `common/report_generator.py:232-248` (OCR 信息渲染部分)

- [ ] **Step 1: 修改 OCR 信息显示判断逻辑**

将原有的"失败时显示"逻辑改为"OCR 相关方法时显示"：

找到以下代码块（约第 232-248 行）：
```python
        # OCR 信息（失败时有 OCR 数据时显示）
        ocr_info = result.get("ocr_info", [])
        if ocr_info and isinstance(ocr_info, list) and len(ocr_info) > 0:
            ocr_items = []
            for item in ocr_info:
                text = item.get("text", "")
                center = item.get("center", {})
                x = center.get("x", "-")
                y = center.get("y", "-")
                if text:
                    ocr_items.append(f'<span class="ocr-text-item">"{text}" ({x}, {y})</span>')
            if ocr_items:
                detail_parts.append(f'''
            <div class="step-ocr-box">
                <div class="step-ocr-label">OCR 识别结果</div>
                <div class="step-ocr-content">{"".join(ocr_items)}</div>
            </div>''')
```

修改为：
```python
        # OCR 信息（OCR 相关方法时显示）
        ocr_info = result.get("ocr_info", [])
        if ocr_info and isinstance(ocr_info, list) and len(ocr_info) > 0:
            # 判断是否是 OCR 相关方法
            if should_show_ocr_info(method):
                ocr_items = []
                for item in ocr_info:
                    text = item.get("text", "")
                    center = item.get("center", {})
                    x = center.get("x", "-")
                    y = center.get("y", "-")
                    if text:
                        ocr_items.append(f'<span class="ocr-text-item">"{text}" ({x}, {y})</span>')
                if ocr_items:
                    detail_parts.append(f'''
            <div class="step-ocr-box">
                <div class="step-ocr-label">OCR 识别结果</div>
                <div class="step-ocr-content">{"".join(ocr_items)}</div>
            </div>''')
```

**关键变化：**
- 注释从"失败时有 OCR 数据时显示"改为"OCR 相关方法时显示"
- 添加 `if should_show_ocr_info(method):` 条件判断
- 移除原有的 `if not success:` 条件限制

- [ ] **Step 2: 验证代码语法正确**

运行: `python -m py_compile common/report_generator.py`
预期: 无错误输出

---

### Task 3: 提交代码

- [ ] **Step 1: 提交修改**

```bash
git add common/report_generator.py
git commit -m "feat: 报告显示所有OCR相关方法的ocr_info信息"
```

---

### Task 4: 验证功能

**验证方法：运行现有测试用例查看报告效果**

- [ ] **Step 1: 运行包含 OCR 操作的测试用例**

选择一个包含 OCR 操作的测试用例运行，生成报告后检查：
- OCR 方法成功时：能看到 OCR 信息（折叠状态）
- OCR 方法失败时：能看到 OCR 信息（展开状态）
- 非 OCR 方法：不显示 OCR 信息

- [ ] **Step 2: 检查生成的 HTML 报告**

打开生成的报告文件，验证：
1. 找到一个 OCR 相关的成功步骤，点击展开，确认能看到 OCR 识别结果
2. 找到一个 OCR 相关的失败步骤，确认默认展开并显示 OCR 识别结果
3. 找到一个非 OCR 方法（如普通点击），确认不显示 OCR 信息

---

## 测试策略

由于这是报告显示逻辑，不需要编写单元测试。通过运行现有测试用例生成报告来验证效果。

**验证点：**
1. OCR 相关方法成功时显示 OCR 信息 ✓
2. OCR 相关方法失败时显示 OCR 信息 ✓
3. 非 OCR 方法不显示 OCR 信息 ✓

---

## 注意事项

1. **显示方式**：成功时折叠，失败时展开（由现有 CSS 样式控制）
2. **方法名判断**：使用集合 `OCR_METHODS` 进行快速查找
3. **不影响执行**：仅修改报告生成逻辑，不影响测试执行流程