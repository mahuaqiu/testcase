# 报告用户标识展示优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 HTML 报告的 AW 调用日志中显示用户标识信息（user_id、account、name）

**Architecture:** 扩展 args 参数传递用户信息，修改 HTML 生成逻辑在 AW 标签旁显示用户信息

**Tech Stack:** Python, HTML/CSS

---

## 文件结构

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `aw/base_aw.py:125-135` | 修改 | 添加 user_account、user_name 到 args |
| `common/report_generator.py:326-328` | 修改 | 清理参数时移除用户信息字段 |
| `common/report_generator.py:369-382` | 修改 | AW 标签旁添加用户信息显示 |
| `common/report_generator.py:CSS部分` | 修改 | 添加 `.log-user-info` 样式 |

---

### Task 1: 修改 base_aw.py 传递用户信息

**Files:**
- Modify: `aw/base_aw.py:125-135`

- [ ] **Step 1: 扩展 args 参数**

将第 125-129 行从：

```python
        # 记录 AW 调用日志
        user_id = self.user.user_id if self.user else ""
        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, **log_args},
```

改为：

```python
        # 记录 AW 调用日志
        user_id = self.user.user_id if self.user else ""
        user_account = self.user.account if self.user else ""
        user_name = self.user.name if self.user else ""
        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
```

- [ ] **Step 2: 同步修改 worker 调用日志（可选，保持一致性）**

将第 138-144 行的 params 也添加用户信息：

```python
        # 记录 worker 调用日志（用于调试，报告中不显示）
        logger.log_worker_call(
            api="task/execute",
            params={"platform": self.PLATFORM, "method": method, "user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
```

- [ ] **Step 3: 提交改动**

```bash
git add aw/base_aw.py
git commit -m "feat: 传递用户 account 和 name 到日志参数"
```

---

### Task 2: 修改 report_generator.py 清理参数

**Files:**
- Modify: `common/report_generator.py:326-328`

- [ ] **Step 1: 扩展清理逻辑**

将第 326-328 行从：

```python
                # 清理参数，移除 user_id 用于显示
                args = log.get("args", {})
                clean_args = {k: v for k, v in args.items() if k != "user_id"}
```

改为：

```python
                # 清理参数，移除用户信息字段用于显示（已在标签旁展示）
                args = log.get("args", {})
                clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name")}
```

- [ ] **Step 2: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat: 清理参数时移除用户信息字段"
```

---

### Task 3: 添加用户信息显示逻辑

**Files:**
- Modify: `common/report_generator.py:320-382`

- [ ] **Step 1: 添加用户信息格式化函数**

在 `_build_logs_html` 方法的 aw_call 分支开头（第 320 行后）添加格式化逻辑：

```python
            elif log_type == "aw_call":
                success = log.get("success", False)
                item_class = "success" if success else "failed"
                status_class = "success" if success else "failed"
                status_text = "成功" if success else "失败"

                # 格式化用户信息显示
                args = log.get("args", {})
                user_id = args.get("user_id", "")
                user_account = args.get("user_account", "")
                user_name = args.get("user_name", "")

                if user_id:
                    if user_name:
                        user_display = f"[{user_id} - {user_name}({user_account})]"
                    elif user_account:
                        user_display = f"[{user_id} - ({user_account})]"
                    else:
                        user_display = f"[{user_id}]"
                else:
                    user_display = "[未知用户]"

                # 清理参数，移除用户信息字段用于显示（已在标签旁展示）
                clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name")}
```

- [ ] **Step 2: 在 HTML 中显示用户信息**

将第 369-382 行从：

```python
                items.append(f"""
            <div class="log-item {item_class}">
                <span class="log-time">{time_str}</span>
                <span class="log-type type-aw_call">AW</span>
                <div class="log-content">
                    <div class="log-main">
                        <span class="log-name">{log.get('aw_name', '')}.{log.get('method', '')}()</span>
                        <span class="log-status {status_class}">{status_text}</span>
                        <span class="log-duration">{log.get('duration_ms', 0)}ms</span>
                    </div>
                    <div class="log-detail">{detail_html}</div>
                    {screenshots_html}
                </div>
            </div>""")
```

改为：

```python
                items.append(f"""
            <div class="log-item {item_class}">
                <span class="log-time">{time_str}</span>
                <span class="log-type type-aw_call">AW</span>
                <span class="log-user-info">{user_display}</span>
                <div class="log-content">
                    <div class="log-main">
                        <span class="log-name">{log.get('aw_name', '')}.{log.get('method', '')}()</span>
                        <span class="log-status {status_class}">{status_text}</span>
                        <span class="log-duration">{log.get('duration_ms', 0)}ms</span>
                    </div>
                    <div class="log-detail">{detail_html}</div>
                    {screenshots_html}
                </div>
            </div>""")
```

- [ ] **Step 3: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat: 在 AW 标签旁显示用户信息"
```

---

### Task 4: 添加 CSS 样式

**Files:**
- Modify: `common/report_generator.py:CSS部分`

- [ ] **Step 1: 添加 `.log-user-info` 样式**

在 CSS 部分（约第 154-166 行，`.type-screenshot` 样式后）添加：

```css
        .log-user-info {{
            background: #e8f5e9;
            color: #2e7d32;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            margin: 0 6px;
        }}
```

注意：在 Python f-string 中 CSS 的 `{}` 需要写成 `{{}}`。

- [ ] **Step 2: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat: 添加用户信息标签 CSS 样式"
```

---

### Task 5: 验证改动

**Files:**
- Run: 测试用例验证

- [ ] **Step 1: 运行现有测试用例生成报告**

```bash
source .venv/bin/activate
pytest testcases/web/waitingroom/test_waitingroom_switch_001.py -v
```

- [ ] **Step 2: 检查生成的 HTML 报告**

打开报告文件，确认：
- AW 标签旁显示用户信息 `[userA - 张三(account123)]`
- 参数详情中不包含 user_id、user_account、user_name
- 样式正确显示（绿色背景）

---

## 完成标准

1. HTML 报告中 AW 调用日志显示用户标识
2. 显示格式：`[user_id - name(account)]` 或简化格式
3. 参数详情不重复显示用户信息
4. 现有测试用例正常运行