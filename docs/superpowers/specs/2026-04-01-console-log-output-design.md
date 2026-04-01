# 日志控制台输出优化设计

## 背景

执行测试用例时，控制台无任何输出，用户无法看到执行进展。同时，报告中包含截图 base64 数据，这些数据不应在控制台打印。

## 目标

1. 将 `aw_call` 和 `step` 类型日志实时输出到控制台
2. 控制台不打印截图 base64 字符串
3. 使用简洁格式，便于快速查看进展

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

在方法末尾添加打印（base64 相关参数不输出）：

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
            aw_name: aw_name,
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

    # 控制台输出（不含 base64）
    status_icon = "✓" if success else "✗"
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {aw_name}.{method}() {status_icon} {duration_ms}ms")
```

**说明**：
- `target_image` 是 base64 字符串，不在控制台打印
- `args` 和 `result` 可能包含 base64，也不打印
- 仅打印关键信息：时间、AW名、方法、状态、耗时

## 输出效果

执行用例时控制台实时输出：

```
14:30:25.123 步骤: 申请用户资源
14:30:28.456 步骤: 执行 hook: start_app
14:30:30.789 LoginAW.ocr_click() ✓ 120ms
14:30:32.012 LoginAW.ocr_input() ✓ 85ms
14:30:35.345 LoginAW.ocr_wait() ✗ 3000ms
```

## 测试验证

修改后执行任意测试用例，确认：
1. 控制台实时显示日志输出
2. 无 base64 字符串打印
3. 格式符合简洁版设计