---
name: testcase-aw
description: "AW新增/扩展/修改。与用户确认平台和操作步骤，生成AW代码并更新INDEX.md。"
---

# AW 操作 Skill

处理AW的新增、扩展、修改操作。

---

## BaseAW 可用方法

生成AW步骤时，只能使用以下方法：

**OCR系列**：`ocr_click`, `ocr_input`, `ocr_wait`, `ocr_assert`, `ocr_get_text`, `ocr_paste`, `ocr_move`

**图像系列**：`image_click`, `image_wait`, `image_assert`, `image_click_near_text`, `image_move`

**坐标系列**：`click`, `move`, `swipe`, `input_text`

**其他**：`press`, `wait`, `start_app`, `stop_app`, `navigate`, `screenshot`

---

## 执行流程

### 步骤 1：确认平台

使用 AskUserQuestion 让用户选择平台：web / windows / mac / ios / android / api

### 步骤 2：确认操作步骤

让用户描述每一步操作：
- UI操作：操作类型 + 操作对象（如 `ocr_click "登录按钮"`）
- API操作：HTTP方法 + 路径 + 参数 + 返回值

### 步骤 3：验证方法存在性

对照上方方法清单，检查每个步骤：
- 方法在清单中 → 直接使用
- 方法不在清单中 → **询问用户**："`{方法名}` 不在可用方法中，请确认操作方式"

### 步骤 4：生成代码 + 更新INDEX.md

---

## 常见编造方法（禁止）

以下方法经常被编造但不存在：
- `ocr_double_click`, `ocr_right_click`, `ocr_scroll`
- `image_double_click`, `drag_and_drop`
- `wait_for_element`, `get_element_text`

---

## 引用其他AW

AW内部调用其他AW时，先读取 INDEX.md 确认目标AW和方法存在。不确定时询问用户。

---

## 代码模板

```python
"""{业务名}业务操作封装。"""

from aw.base_aw import BaseAW

class XxxAW(BaseAW):
    PLATFORM = "{平台}"

    def do_xxx(self):
        """{业务动作}。"""
        self.ocr_click("按钮")

    def should_xxx_success(self):
        """断言{期望}。"""
        self.ocr_wait("成功")
```

---

## 核心原则

1. 不确定的方法 → 问用户确认
2. 使用 `self.ocr_click()` 而非 `self.client.ocr_click()`
3. 生成后更新 INDEX.md