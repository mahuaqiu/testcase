# AW 索引（持久记忆区）

> 本文件是 AW 资源的快速索引，用于测试用例生成时快速查找可复用的 AW。
>
> **更新规则**：新增/扩展 AW 后必须同步更新本文件。

---

## Web 端 AW

### LoginAW

> 文件路径：`aw/web/login_aw.py`
> 功能概述：Web 登录流程

| 方法 | 说明 |
|------|------|
| `do_navigate_to_login(url)` | 导航到登录页面 |
| `do_login(username=None, password=None)` | 执行登录操作 |
| `do_accept_privacy()` | 接受隐私政策 |
| `should_login_success()` | 断言登录成功 |
| `should_show_error(error_msg)` | 断言显示错误提示 |

### MeetingJoinAW

> 文件路径：`aw/web/meeting_join_aw.py`
> 功能概述：Web 入会流程

| 方法 | 说明 |
|------|------|
| `do_join_as_host(meeting)` | 主持人入会 |
| `do_join_as_guest(meeting)` | 与会者入会 |
| `do_leave()` | 离会 |
| `do_admit_participant(name=None)` | 主持人准入与会者（可选指定用户名） |
| `should_join_success(number)` | 断言入会成功，验证会议人数（number: 期望人数） |
| `should_in_waitingroom()` | 断言在等候室中 |
| `should_leave_success()` | 断言离会成功 |

### MeetingControlAW

> 文件路径：`aw/web/meeting_control_aw.py`
> 功能概述：Web 会议控制栏操作

| 方法 | 说明 |
|------|------|
| `do_trigger_control_bar()` | 触发会控栏显示 |

### InitAW

> 文件路径：`aw/web/init_aw.py`
> 功能概述：Web 应用初始化

| 方法 | 说明 |
|------|------|
| `do_start_app(browser="chrome")` | 启动浏览器 |
| `do_stop_app(browser="chrome")` | 关闭浏览器 |

---

## API AW

### MeetingManageAW

> 文件路径：`aw/api/meeting_manage_aw.py`
> 功能概述：会议预约/取消/查询

| 方法 | 说明 |
|------|------|
| `do_login()` | 显式登录获取 token |
| `do_create_meeting(subject, **kwargs)` | 预约/创建会议，返回 MeetingInfo；kwargs 可传入 enableWaitingRoom 开启等候室 |
| `do_cancel_meeting(conference_id)` | 取消指定会议 |
| `do_query_meetings(limit=10)` | 查询我的会议列表 |
| `do_cancel_all_meetings()` | 取消所有会议 |

### WebinarManageAW

> 文件路径：`aw/api/webinar_manage_aw.py`
> 功能概述：网络研讨会创建/取消/查询

| 方法 | 说明 |
|------|------|
| `do_create_webinar(subject)` | 创建网络研讨会，返回 WebinarInfo；vmrID 从 user.vmrID 自动获取；beginTime/duration 未传时使用默认值 |
| `do_cancel_webinar(conference_id)` | 取消指定网络研讨会 |
| `do_query_webinars(page_num=1, page_size=10)` | 查询网络研讨会列表 |
| `do_cancel_all_webinars()` | 取消所有网络研讨会 |

### MeetingControlAW

> 文件路径：`aw/api/meeting_control_aw.py`
> 功能概述：会议控制（等候室等）

| 方法 | 说明 |
|------|------|
| `do_get_region_info(conference_id, chair_password)` | 获取会议站点信息 |
| `do_get_control_token(conference_id, chair_password)` | 获取会议控制 token |
| `do_set_waiting_room(conference_id, chair_password, enable)` | 设置等候室开关 |

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
| `activate_window(value, match_by="title")` | 激活窗口（仅桌面端） |

### CheckAW

> 文件路径：`aw/common/check_aw.py`
> 功能概述：公共检查操作封装

| 方法 | 说明 |
|------|------|
| `should_toast_exists(text)` | 断言toast提示文字存在 |

---

## 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| 业务方法 | `do_{动作}` | `do_login()` |
| 断言方法 | `should_{期望}` | `should_login_success()` |