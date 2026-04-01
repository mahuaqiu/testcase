# 日志控制台输出优化设计

## 背景

执行测试用例时，控制台无任何输出，用户无法看到执行进展。同时，报告中包含截图 base64 数据，这些数据不应在控制台打印。

## 目标

1. 将 `aw_call` 和 `step` 类型日志实时输出到控制台
2. 控制台显示关键操作参数（如点击的文本、输入的内容）
3. 控制台不打印截图 base64 字符串和内部参数
4. 使用简洁格式，便于快速查看进展

## 方案

在 `ReportLogger` 的 `log_step` 和 `log_aw_call` 方法末尾直接添加 `print()` 调用。

**优点**：
- 改动最小，集中一处
- 无需引入新类或复杂机制
- 实时输出，用例执行过程中可见进展

## 修改内容

### 文件：`common/report_logger.py`

#### 1. `log_step` 方法

在方法末尾添加打印：

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

#### 2. `log_aw_call` 方法

在方法末尾添加打印，格式化关键参数：

```python
def log_aw_call(
    self,
    aw_name: str,
    method: str,
    args: dict,
    success: bool,
    result: dict,
    duration_ms: int,
    target_image: str = "",
    target_image_path: str = ""
) -> None:
    """记录 AW 方法调用。"""
    with self._lock:
        log_entry = {
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "type": "aw_call",
            "aw_name": aw_name,
            "method": method,
            "args": args,
            "success": success,
            "result": result,
            "duration_ms": duration_ms,
            "target_image": target_image,
            "target_image_path": target_image_path
        }
        self._logs.append(log_entry)
        if not success:
            self._last_failed_aw = log_entry

    # 控制台输出（过滤参数，不含 base64）
    display_args = self._filter_display_args(args)
    args_str = self._format_args(display_args)
    status_icon = "✓" if success else "✗"
    if args_str:
        print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {aw_name}.{method}({args_str}) {status_icon} {duration_ms}ms")
    else:
        print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {aw_name}.{method}() {status_icon} {duration_ms}ms")
```

#### 3. 新增辅助方法

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

def _filter_display_args(self, args: dict) -> dict:
    """过滤参数，只保留需要显示的。"""
    return {
        k: v for k, v in args.items()
        if k in self._DISPLAY_ARGS and not k in self._HIDDEN_ARGS
    }

def _format_args(self, args: dict) -> str:
    """格式化参数为字符串。"""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        # 字符串值加引号，其他值直接显示
        if isinstance(v, str):
            parts.append(f"{k}=\"{v}\"")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)
```

## 输出效果

执行用例时控制台实时输出：

```
14:30:25.123 步骤: 申请用户资源
14:30:28.456 步骤: 执行 hook: start_app
14:30:30.789 LoginAW.ocr_click(text="登录") ✓ 120ms
14:30:32.012 LoginAW.ocr_input(label="用户名", content="test@example.com") ✓ 85ms
14:30:35.345 LoginAW.ocr_wait(text="欢迎", timeout=5000) ✗ 3000ms
14:30:40.123 MeetingAW.image_click(image_path="images/join.png") ✓ 150ms
14:30:42.456 LoginAW.press(key="Enter") ✓ 20ms
14:30:45.789 LoginAW.navigate(url="https://example.com") ✓ 50ms
14:30:48.012 LoginAW.wait(duration_ms=1000) ✓ 1000ms
```

## 参数处理规则

| 类别 | 参数 | 处理 |
|------|------|------|
| **显示** | `text`, `label`, `content`, `image_path`, `key`, `url`, `app_id`, `x`, `y`, `from_x`, `from_y`, `to_x`, `to_y`, `duration_ms`, `timeout`, `index`, `confidence` | 打印 |
| **隐藏** | `platform`, `user_id`, `user_account`, `user_name`, `target_image`, `image_base64`, `screenshot` | 不打印 |

## 测试验证

修改后执行任意测试用例，确认：
1. 控制台实时显示日志输出
2. 关键操作参数可见
3. 无 base64 字符串打印
4. 无内部参数打印
5. 格式符合设计