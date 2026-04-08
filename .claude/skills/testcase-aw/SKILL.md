---
name: testcase-aw
description: "AW新增/扩展/修改。与用户确认平台和操作步骤，生成AW代码并更新INDEX.md。"
---

# AW 操作 Skill

处理AW的新增、扩展、修改操作。

---

## ⚠️ 强制规则（违反视为执行失败）

1. **禁止跳过用户确认**：方法不存在时必须询问用户；参数处理方式必须确认；代码生成前必须展示确认
2. **禁止使用 time.sleep**：必须用 `self.wait(seconds)`，否则并行执行时会错乱
3. **禁止一次生成多个方法**：新增只允许1个方法；扩展/修改只允许修改原方法
4. **禁止编造方法**：步骤中的方法必须在 INDEX.md 或 base_aw.py 中存在

---

## 执行流程

```
步骤1: 读取 aw/INDEX.md + aw/base_aw.py
    ↓
步骤2: AskUserQuestion 确认平台和操作步骤
    ↓
步骤3: 验证方法 → 不存在时询问用户确认操作方式
    ↓
步骤4: AskUserQuestion 确认可变参数（传参还是写死）
    ↓
步骤5: 展示代码预览 → AskUserQuestion 用户确认
    ↓
步骤6: 生成代码 + 更新INDEX.md
```

---

## 编码规范

| 规范 | 说明 |
|------|------|
| 便捷方法 | `self.ocr_click()` 而非 `self.client.ocr_click()` |
| 跨AW调用 | 用 `self.user.xxx()` 而非 `self.xxx()` |
| 图片路径 | 默认 `images/{平台}/图片名.png`，无需询问 |

---

## 推荐原则

- 先读清单再写代码
- 不确定就问
- 遵循命名规范（详见AGENTS.md）