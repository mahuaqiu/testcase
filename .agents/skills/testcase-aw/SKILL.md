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
- `aw/INDEX.md` — 功能速查表（确认功能归属）
- `aw/{平台}/INDEX.md` — 平台已有 AW 及方法

### 步骤 2：确认平台和步骤

使用 AskUserQuestion 让用户选择平台，描述操作步骤。

### 步骤 3：验证方法

对照已读取的清单检查每个步骤：
- 方法存在 → 直接使用
- 方法不存在 → **询问用户确认操作方式**

### 步骤 4：参数确认（重要）

如果用户输入的操作步骤中包含**可变参数**（如用户名、会议主题、文件名等），**必须**询问用户：
- 该参数是否需要支持 AW 方法传参？
- 还是直接写死在步骤里？

使用 AskUserQuestion 确认每个参数的处理方式。

### 步骤 5：生成前确认

**生成代码前必须与用户确认**：
- 展示即将生成的代码预览或方法签名
- 使用 AskUserQuestion 让用户确认是否继续
- 用户确认后再执行代码生成

### 步骤 6：生成代码 + 更新索引

1. 新增 AW：更新 `aw/{平台}/INDEX.md` 详细记录
2. 新增功能类型：更新 `aw/INDEX.md` 功能速查表

---

## 核心规则

1. **先读清单再写代码**：步骤中的方法必须在平台索引或主索引的公共 AW 中存在
2. **不确定就问**：方法不存在时，询问用户而非编造
3. **便捷方法**：用 `self.ocr_click()` 而非 `self.client.ocr_click()`
4. **禁止使用 time.sleep**：AW 中必须使用 `self.wait(seconds)` 而非 `time.sleep()`，单位为秒（与 time.sleep 一致），否则在 `with parallel()` 并行执行时 sleep 会提前执行导致时序错乱。**测试用例（testcase）中**如需固定等待，直接使用 `time.sleep(x)` 而非 `self.wait()`——用例代码不通过 AW 的并行代理层，`self.wait()` 在用例中不适用。
5. **跨 AW 类调用**：调用其他 AW 类的方法时，必须用 `self.user.xxx()` 而非 `self.xxx()`。例如 `MeetingJoinAW` 中调用 `MeetingControlAW.do_trigger_control_bar()`，应写 `self.user.do_trigger_control_bar()`
6. **新增限制**：AW 新增时，**只允许生成一个方法**，不能一次生成多个方法
7. **修改限制**：AW 扩展或修改时，**只允许在原方法上修改**，不允许生成新方法
8. **参数确认**：步骤中的可变参数必须与用户确认是传参还是写死
9. **生成前确认**：代码生成前必须展示给用户确认
10. **图片路径默认规则**：涉及图片操作（`image_click`、`image_wait`、`image_assert` 等）时，默认路径为 `images/{平台}/图片名.png`，无需询问路径。例如用户说"点击挂断按钮图片"，平台为 web，则理解为 `images/web/挂断.png`
11. **Worker 生命周期由基建处理**：AW 不直接调用 `execute_async`、`get_task`、`cancel_task`，不根据 `accepted/running/cancelling` 等状态编写业务分支；只使用 BaseAW 原子方法。
12. **错误处理边界**：AW 方法保留业务语义和原有参数/返回约定，直接让 `AWError`、`TestagentError` 向上抛出，不自行根据英文错误字符串重试或吞错。
13. **并行兼容性**：AW 方法在 `with parallel()` 中必须只表达动作收集；需要返回值的动作、依赖前一步结果的动作和断言应放到并行上下文外。
14. **AW 日志**：需要补充业务上下文时使用 `self.log("日志内容")`，会自动归入当前 `do_*/should_*` 步骤；OCR、图像、坐标、等待等原子操作已由 `BaseAW` 自动记录，无需重复记录或直接调用 `ReportLogger`。
15. **日志标题规范**：`do_*/should_*` 方法的 docstring 首行会作为 HTML 报告标题，必须是简短中文动作描述；业务日志内容应描述关键业务状态或分支，不要重复方法名和底层动作名。

16. **多用户/多端 hooks 控制支持**：

新增 AW 时，文档/用例作者可使用以下方式控制 hooks：

```python
@pytest.mark.users({"userA": "windows", "userB": "mac"})
@pytest.mark.hooks(
    userA={"setup": ["+login"]},           # 仅 userA 执行 setup 登录
    userB={"teardown": ["-stop_app"]},     # 仅 userB 跳过关应用
    # windows={"setup": ["+login"]},        # 该平台全部用户
    userA_api={"teardown": ["-cancel_all_meetings"]},  # 按需控制 API 用户
)
```

**合并优先级**（每个用户独立计算）：
1. 平台默认（config.yaml）
2. 用例全局 hooks
3. 用例平台键
4. 用例用户键（最终层）

**API 用户**：`userA` 的 `userA` 键**不影响** `userA_api`；改 API 用户需显式写 `userA_api=...` 或 `api=...`。
