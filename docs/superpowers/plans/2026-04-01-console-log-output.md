# 日志控制台输出优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在控制台实时输出 AW 调用和步骤日志，显示关键操作参数，隐藏 base64 和内部参数。

**Architecture:** 在 ReportLogger 类中添加 print() 调用和辅助方法，实时输出简洁格式的日志。

**Tech Stack:** Python, pytest

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `common/report_logger.py` | 修改 | 添加控制台输出逻辑 |

---

### Task 1: 添加类常量和辅助方法

**Files:**
- Modify: `common/report_logger.py:8-33` (类定义开头)

- [ ] **Step 1: 添加类常量**

在 `ReportLogger` 类中，`_local` 定义之后添加：

```python
    # 需要显示的参数名（有意义的关键参数）
    _DISPLAY_ARGS = {
        "text", "label", "content", "image_path", "key", "url",
        "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
        "duration_ms", "timeout", "index", "confidence"
    }

    # 不显示的参数名（内部参数或 base64）
    _HIDDEN_ARGS = {
        "platform", "user_id", "user_account", "user_name",
        "target_image", "image_base64", "screenshot"
    }
```

- [ ] **Step 2: 添加 `_filter_display_args` 方法**

在 `__init__` 方法之后添加：

```python
    def _filter_display_args(self, args: dict) -> dict:
        """过滤参数，只保留需要显示的。"""
        return {
            k: v for k, v in args.items()
            if k in self._DISPLAY_ARGS and k not in self._HIDDEN_ARGS
        }
```

- [ ] **Step 3: 添加 `_format_args` 方法**

在 `_filter_display_args` 方法之后添加：

```python
    def _format_args(self, args: dict) -> str:
        """格式化参数为字符串。"""
        if not args:
            return ""
        parts = []
        for k, v in args.items():
            # 字符串值加引号，其他值直接显示
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)
```

---

### Task 2: 修改 log_step 方法

**Files:**
- Modify: `common/report_logger.py:35-43` (log_step 方法)

- [ ] **Step 1: 添加控制台输出**

在 `log_step` 方法末尾（`with` 块之后）添加：

```python
        # 控制台输出
        print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} 步骤: {step}")
```

修改后的完整方法：

```python
    def log_step(self, step: str, detail: str = "") -> None:
        """记录测试步骤。"""
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "step",
                "step": step,
                "detail": detail
            })
        # 控制台输出
        print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} 步骤: {step}")
```

---

### Task 3: 修改 log_aw_call 方法

**Files:**
- Modify: `common/report_logger.py:45-84` (log_aw_call 方法)

- [ ] **Step 1: 添加控制台输出逻辑**

在 `log_aw_call` 方法末尾（`with` 块之后）添加：

```python
        # 控制台输出（过滤参数，不含 base64）
        display_args = self._filter_display_args(args)
        args_str = self._format_args(display_args)
        status_icon = "✓" if success else "✗"
        time_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if args_str:
            print(f"{time_str} {aw_name}.{method}({args_str}) {status_icon} {duration_ms}ms")
        else:
            print(f"{time_str} {aw_name}.{method}() {status_icon} {duration_ms}ms")
```

---

### Task 4: 验证实现

**Files:**
- None (运行现有测试用例验证)

- [ ] **Step 1: 执行测试用例**

运行任意现有测试用例，观察控制台输出：

```bash
source .venv/bin/activate && pytest testcases/web/waitingroom/test_waitingroom_host_join_001.py -v
```

- [ ] **Step 2: 验证输出格式**

确认控制台输出符合预期格式：
- 步骤日志：`HH:MM:SS.mmm 步骤: xxx`
- AW 调用：`HH:MM:SS.mmm AW名.方法(参数) ✓/✗ 耗时ms`
- 无 base64 字符串
- 无内部参数（platform, user_id 等）

---

### Task 5: 提交变更

**Files:**
- None (git commit)

- [ ] **Step 1: 提交代码**

```bash
git add common/report_logger.py
git commit -m "feat: 日志实时输出到控制台，显示关键操作参数"
```