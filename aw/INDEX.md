# AW 索引

> 本文件是公共 AW 资源索引及平台导航。各平台专属 AW 请跳转对应索引。
>
> **更新规则**：新增 AW 后必须同步更新平台索引；新增功能类型时更新功能速查表。

---

## 功能速查表

| 功能 | 支持平台 |
|------|----------|
| Login | Web, Windows, Mac, iOS, Android |
| MeetingJoin | Web, Windows, Mac, iOS, Android |
| MeetingControl | Web, Windows, Mac, iOS, Android, API |
| MeetingManage | API |
| WebinarManage | API |
| Init | Web, Windows, Mac, iOS, Android |

---

## 公共 AW

### BaseAW

> 文件路径：`aw/base_aw.py`
> 功能概述：AW 基类，提供所有平台通用的便捷方法

**OCR 文字识别动作：**

| 方法 | 说明 |
|------|------|
| `ocr_click(text, **kwargs)` | OCR 识别并点击文字 |
| `ocr_input(label, content, **kwargs)` | OCR 定位后输入文本 |
| `ocr_wait(text, **kwargs)` | 等待文字出现 |
| `ocr_assert(text, **kwargs)` | 断言文字存在 |
| `ocr_get_text(**kwargs)` | 获取屏幕所有文字 |
| `ocr_paste(text, content, **kwargs)` | OCR 定位后粘贴剪贴板内容 |
| `ocr_move(text, **kwargs)` | OCR 定位后移动鼠标（仅桌面端） |
| `ocr_double_click(text, **kwargs)` | OCR 定位后双击文字 |
| `ocr_exist(text, **kwargs)` | 检查文字是否存在（返回 bool） |
| `ocr_get_position(text, **kwargs)` | 获取文字坐标列表 |
| `ocr_click_same_row_text(anchor_text, target_text, **kwargs)` | 点击锚点文本同一行的目标文本 |
| `ocr_click_same_row_image(anchor_text, image_path, **kwargs)` | 点击锚点文本同一行的目标图片 |
| `ocr_check_same_row_text(anchor_text, target_text, **kwargs)` | 检查锚点文本同一行的目标文本是否存在 |
| `ocr_check_same_row_image(anchor_text, image_path, **kwargs)` | 检查锚点文本同一行的目标图片是否存在 |

**图像识别动作：**

| 方法 | 说明 |
|------|------|
| `image_click(image_path, **kwargs)` | 图像识别点击 |
| `image_wait(image_path, **kwargs)` | 等待图像出现 |
| `image_assert(image_path, **kwargs)` | 断言图像存在 |
| `image_click_near_text(image_path, text, **kwargs)` | 点击文本附近最近的图像 |
| `image_move(image_path, **kwargs)` | 图像识别后移动鼠标（仅桌面端） |
| `image_double_click(image_path, **kwargs)` | 图像识别后双击 |
| `image_exist(image_path, **kwargs)` | 检查图像是否存在（返回 bool） |
| `image_get_position(image_path, **kwargs)` | 获取图像坐标列表 |

**坐标动作：**

| 方法 | 说明 |
|------|------|
| `click(x, y)` | 坐标点击 |
| `right_click(x, y, **kwargs)` | 右键点击指定坐标（仅桌面端） |
| `double_click(x, y, **kwargs)` | 坐标双击 |
| `move(x, y, **kwargs)` | 移动鼠标到指定坐标（仅桌面端） |
| `swipe(from_x, from_y, to_x, to_y, **kwargs)` | 滑动操作 |
| `drag(from_x, from_y, to_x, to_y, **kwargs)` | 拖拽操作（参数与 swipe 一致） |
| `input_text(x, y, text)` | 在指定坐标输入文本 |

> **注**：`swipe` 和 `drag` 参数完全一致，功能相同，可根据语义选用。

**其他动作：**

| 方法 | 说明 |
|------|------|
| `press(key)` | 按键操作 |
| `wait(duration)` | 固定等待（秒） |
| `start_app(app_id)` | 启动应用 |
| `stop_app(app_id)` | 关闭应用 |
| `navigate(url)` | 导航到 URL（Web 端专用） |
| `new_page()` | 创建新空白标签页（Web 端专用） |
| `switched_page(page_index)` | 切换到指定页面（Web 端专用） |
| `close_page()` | 关闭当前页面（Web 端专用） |
| `cmd_exec(command, **kwargs)` | 在宿主机执行命令 |
| `screenshot()` | 截图并返回 base64 |
| `activate_window(value, match_by="title", name=None)` | 激活窗口（Windows/Mac/Web），match_by 支持 title/class，name 可过滤进程 exe |

**Windows 系统控制动作：**

| 方法 | 说明 |
|------|------|
| `set_resolution(width, height, monitor_index=0)` | 设置显示器分辨率（仅 Windows） |
| `set_volume(value)` | 设置系统音量（仅 Windows，value 为 0-100） |
| `audio_device(device, state)` | 启用/停用音频设备（仅 Windows，state 为 enable/disabled） |

### CheckAW

> 文件路径：`aw/common/check_aw.py`
> 功能概述：公共检查操作封装

| 方法 | 说明 |
|------|------|
| `should_toast_exists(text)` | 断言 toast 提示文字存在 |

---

## 平台索引

| 平台 | 索引文件 |
|------|----------|
| Web | [web/INDEX.md](web/INDEX.md) |
| Windows | [windows/INDEX.md](windows/INDEX.md) |
| Mac | [mac/INDEX.md](mac/INDEX.md) |
| iOS | [ios/INDEX.md](ios/INDEX.md) |
| Android | [android/INDEX.md](android/INDEX.md) |
| API | [api/INDEX.md](api/INDEX.md) |

---

## 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| 业务方法 | `do_{动作}` | `do_login()` |
| 断言方法 | `should_{期望}` | `should_login_success()` |