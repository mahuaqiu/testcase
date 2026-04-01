# 报告用户标识展示优化

## 背景

当前多用户并行执行测试用例时，HTML 报告中的 AW 调用日志缺少用户标识信息，导致难以区分不同用户的操作。

例如：
```
with parallel():
    userA.do_join_as_host(meeting)
    userB.do_join_as_guest(meeting)
```

报告只显示 `LoginAW.do_join_as_host()` 和 `LoginAW.do_join_as_guest()`，看不出是 userA 还是 userB 调用的。

## 目标

在 AW 标签旁显示用户标识信息，格式：`AW [userA - 张三(account123)]`

## 设计

### 改动点

**1. `aw/base_aw.py` - `_execute_with_log` 方法**

在第 125-135 行，扩展 args 参数传递用户信息：

```python
# 当前
user_id = self.user.user_id if self.user else ""

# 改为
user_id = self.user.user_id if self.user else ""
user_account = self.user.account if self.user else ""
user_name = self.user.name if self.user else ""
log_args_with_user = {
    "user_id": user_id,
    "user_account": user_account,
    "user_name": user_name,
    **log_args
}
```

**2. `common/report_generator.py` - `_build_logs_html` 方法**

修改 aw_call 类型的日志显示（约第 320-382 行）：

```html
<!-- 当前 -->
<span class="log-type type-aw_call">AW</span>

<!-- 改为 -->
<span class="log-type type-aw_call">AW</span>
<span class="log-user-info">[userA - 张三(account123)]</span>
```

显示逻辑：
- 如果有 user_name：显示 `[user_id - user_name(user_account)]`
- 如果无 user_name 但有 account：显示 `[user_id - (user_account)]`
- 如果只有 user_id：显示 `[user_id]`

**3. `common/report_generator.py` - `_clean_response_for_display` 方法**

移除 user_account、user_name 字段（类似当前移除 user_id 的处理），避免在参数详情中重复显示。

**4. CSS 样式**

添加 `.log-user-info` 样式：

```css
.log-user-info {
    background: #e8f5e9;
    color: #2e7d32;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    margin: 0 6px;
}
```

### 影响范围

- `aw/base_aw.py`：约 5 行改动
- `common/report_generator.py`：约 20 行改动
- 不影响 `common/report_logger.py`（args 字典自动包含新字段）

### 兼容性

- 向后兼容：如果 user 为空，显示 `[未知用户]`
- API User 正常显示（user_id 以 `_api` 结尾）