---
name: testcase-aw
description: "AW新增/扩展/修改。与用户确认平台和操作步骤，生成AW代码并更新INDEX.md。"
---

# AW 操作 Skill

处理AW的新增、扩展、修改操作。

---

## 执行流程

### 步骤 1：读取可用资源

**必须先读取**：
- `aw/INDEX.md` — 已有 AW 及方法
- `aw/base_aw.py` — BaseAW 基础方法

### 步骤 2：确认平台和步骤

使用 AskUserQuestion 让用户选择平台，描述操作步骤。

### 步骤 3：验证方法

对照已读取的清单检查每个步骤：
- 方法存在 → 直接使用
- 方法不存在 → **询问用户确认操作方式**

### 步骤 4：生成代码 + 更新INDEX.md

---

## 核心规则

1. **先读清单再写代码**：步骤中的方法必须在 INDEX.md 或 base_aw.py 中存在
2. **不确定就问**：方法不存在时，询问用户而非编造
3. **便捷方法**：用 `self.ocr_click()` 而非 `self.client.ocr_click()`
4. **禁止使用 time.sleep**：AW 中必须使用 `self.wait(seconds)` 而非 `time.sleep()`，单位为秒（与 time.sleep 一致），否则在 `with parallel()` 并行执行时 sleep 会提前执行导致时序错乱