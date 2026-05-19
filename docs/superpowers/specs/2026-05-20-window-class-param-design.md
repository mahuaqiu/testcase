# AW 层 window_class 参数适配设计

## 背景

api.yaml 中 Windows 平台支持窗口级截图（通过 `WindowSpec` 参数），可在任务级别传递 `title` 或 `class` 来绑定特定窗口。绑定后，所有 OCR/Image 操作都会只截取该窗口区域，坐标自动从窗口相对坐标转换为全局坐标。

当前 AW 层未适配此参数，需要在 AW 方法中支持传递 `window_class` 参数。

## 目标

- AW 层 OCR/Image 方法支持 `window_class` 参数
- 参数仅对 Windows 平台生效
- 与 `region` 参数处理方式类似，作为 TaskRequest 级别参数传递

## API 定义（来自 api.yaml）

```yaml
WindowSpec:
  type: object
  description: 窗口定位参数（Windows 平台），用于窗口级截图。
  properties:
    title:
      type: string
      description: 窗口标题（包含匹配），如 '华为云会议'
    class:
      type: string
      description: 窗口类名（精确匹配），如 'HwmMainWndClass'
```

本次只实现 `class` 参数。

## 设计方案

### 1. TestagentClient 修改

`execute()` 方法添加 `window` 参数：

```python
def execute(
    self,
    platform: str,
    actions: List[Dict[str, Any]],
    device_id: Optional[str] = None,
    user_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    level: Optional[str] = None,
    window: Optional[Dict[str, Any]] = None,  # 新增
) -> Dict[str, Any]:
    task_request = {
        "platform": platform,
        "actions": actions,
    }
    if device_id:
        task_request["device_id"] = device_id
    if user_id:
        task_request["user_id"] = user_id
    if config:
        task_request["config"] = config
    if level:
        task_request["level"] = level
    if window:
        task_request["window"] = window  # 新增

    return self._request("POST", "/task/execute", data=task_request)
```

### 2. BaseAW 修改

#### 2.1 新增 `_build_window()` 方法

```python
def _build_window(self, window_class: str | None) -> dict | None:
    """构建 window 参数（仅 Windows 平台）。

    Args:
        window_class: 窗口类名（精确匹配）。

    Returns:
        {"class": window_class} 或 None。
    """
    if not window_class:
        return None

    # 公共 AW 继承 User 的平台
    platform = self.PLATFORM
    if platform == "common" and self.user:
        platform = self.user.platform

    # 仅 Windows 平台生效
    if platform != "windows":
        logger.warning(f"window_class only works on Windows, current: {platform}")
        return None

    return {"class": window_class}
```

#### 2.2 修改 `_execute_with_log()` 签名

添加 `window` 参数：

```python
def _execute_with_log(
    self,
    method: str,
    action_data: Dict[str, Any],
    log_args: Dict[str, Any],
    window: Optional[Dict[str, Any]] = None,  # 新增
) -> Dict[str, Any]:
    ...
    # iOS/Android 平台需要 device_id
    device_id = None
    if platform in ("ios", "android") and self.user:
        device_id = self.user.device_id
    result = self.client.execute(platform, [action_data], device_id=device_id, window=window)  # 新增
```

#### 2.3 修改 `_execute_exist_check()` 签名

同样添加 `window` 参数：

```python
def _execute_exist_check(
    self,
    method: str,
    action_data: Dict[str, Any],
    log_args: Dict[str, Any],
    window: Optional[Dict[str, Any]] = None,  # 新增
) -> Dict[str, Any]:
    ...
    result = self.client.execute(platform, [action_data], device_id=device_id, window=window)  # 新增
```

#### 2.4 修改 `_exec()` 签名

```python
def _exec(
    self,
    action_type: str,
    action_data: dict,
    log_args: dict,
    window: dict | None = None,  # 新增
) -> dict:
    full_action_data = {"action_type": action_type, **action_data}
    return self._execute_with_log(action_type, full_action_data, log_args, window=window)
```

#### 2.5 修改 `_exec_bool()` 和 `_exec_list()`

```python
def _exec_bool(self, action_type: str, action_data: dict, log_args: dict, window: dict | None = None) -> bool:
    full_action_data = {"action_type": action_type, **action_data}
    result = self._execute_exist_check(action_type, full_action_data, log_args, window=window)
    return result.get("exists", False)

def _exec_list(self, action_type: str, action_data: dict, log_args: dict, key: str = "positions", window: dict | None = None) -> list:
    result = self._exec(action_type, action_data, log_args, window=window)
    ...
```

### 3. OCR/Image 方法添加 window_class 参数

#### OCR 方法（12个）

| 方法 | 修改内容 |
|------|----------|
| `ocr_click` | 添加 `window_class: str = None` 参数，调用 `_build_window()`，传给 `_exec()` |
| `ocr_input` | 同上 |
| `ocr_wait` | 同上 |
| `ocr_assert` | 同上 |
| `ocr_get_text` | 同上，传给 `_exec_str()` |
| `ocr_paste` | 同上 |
| `ocr_move` | 同上 |
| `ocr_double_click` | 同上 |
| `ocr_exist` | 同上，传给 `_exec_bool()` |
| `ocr_get_position` | 同上，传给 `_exec_list()` |
| `ocr_click_same_row_text` | 同上 |
| `ocr_click_same_row_image` | 同上 |
| `ocr_check_same_row_text` | 同上，传给 `_exec_bool()` |
| `ocr_check_same_row_image` | 同上，传给 `_exec_bool()` |

#### Image 方法（8个）

| 方法 | 修改内容 |
|------|----------|
| `image_click` | 添加 `window_class: str = None` 参数 |
| `image_wait` | 同上 |
| `image_assert` | 同上 |
| `image_click_near_text` | 同上 |
| `image_move` | 同上 |
| `image_double_click` | 同上 |
| `image_exist` | 同上，传给 `_exec_bool()` |
| `image_get_position` | 同上，传给 `_exec_list()` |

### 4. 方法签名示例

```python
def ocr_click(self, text: str, window_class: str = None, **kwargs) -> dict:
    """OCR 识别并点击。

    Args:
        text: 要识别并点击的文字。
        window_class: 窗口类名（仅 Windows 平台，精确匹配），如 "HwmMainWndClass"。
        timeout: 超时时间（秒），默认 5。
        index: 选择第几个匹配结果（从 0 开始）。
        offset: 点击偏移量 {"x": 0, "y": 0}。
        click_duration: 点击持续时间（毫秒），用于长按。
        region: 操作区域名称或坐标 [x1, y1, x2, y2]。
        level: 执行层级（仅 Web），browser 或 system。
        monitor: 显示器编号（仅 Web，配合 level: system）。

    示例:
        # Windows 平台绑定窗口后执行 OCR
        userA.ocr_click("登录", window_class="HwmMainWndClass")
    """
    window = self._build_window(window_class)
    params = self._ocr_params(kwargs)
    if "click_duration" in kwargs:
        params["click_duration"] = kwargs["click_duration"]
    return self._exec("ocr_click",
        {"value": text, **params},
        {"text": text, **kwargs},
        window=window)
```

### 5. 使用示例

```python
# Windows 平台测试用例
@pytest.mark.users({"userA": "windows"})
class TestClass:
    def test_window_ocr(self, users):
        userA = users["userA"]

        # 绑定窗口后执行 OCR 点击
        userA.ocr_click("登录", window_class="HwmMainWndClass")

        # 绑定窗口后等待文字出现
        userA.ocr_wait("会议中", window_class="HwmMainWndClass", timeout=10)

        # 绑定窗口后断言文字存在
        userA.ocr_assert("参会人", window_class="HwmMainWndClass")

        # 绑定窗口后执行图像点击
        userA.image_click("images/icon.png", window_class="HwmMainWndClass")
```

## 实现步骤

1. **TestagentClient 修改**：`execute()` 方法添加 `window` 参数
2. **BaseAW 基础方法修改**：
   - 新增 `_build_window()` 方法
   - 修改 `_execute_with_log()` 签名
   - 修改 `_execute_exist_check()` 签名
   - 修改 `_exec()`、`_exec_bool()`、`_exec_str()`、`_exec_list()` 签名
3. **OCR 方法修改**：12 个方法添加 `window_class` 参数
4. **Image 方法修改**：8 个方法添加 `window_class` 参数

## 测试验证

- 单元测试：验证 `_build_window()` 方法在不同平台下的行为
- 集成测试：Windows 平台实际绑定窗口执行 OCR/Image 操作
- 边界测试：非 Windows 平台传 `window_class` 参数时应忽略并输出警告日志