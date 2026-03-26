# AW 索引（持久记忆区）

> 本文件是 AW 资源的快速索引，用于测试用例生成时快速查找可复用的 AW。
>
> **更新规则**：新增/扩展 AW 后必须同步更新本文件。

---

## Web 端 AW

| AW 类 | 文件路径 | 功能概述 | 方法列表 |
|-------|----------|----------|----------|
| LoginAW | aw/web/login_aw.py | Web 登录流程 | do_navigate_to_login(), do_login(), do_accept_privacy(), should_login_success(), should_show_error() |
| MeetingJoinAW | aw/web/meeting_join_aw.py | Web 入会流程 | do_join_as_host(), do_join_as_guest(), do_leave(), do_admit_participant(), should_join_success(), should_in_waitingroom(), should_leave_success() |
| InitAW | aw/web/init_aw.py | Web 应用初始化 | do_start_app(), do_stop_app() |

---

## API AW

| AW 类 | 文件路径 | 功能概述 | 方法列表 |
|-------|----------|----------|----------|
| MeetingManageAW | aw/api/meeting_manage_aw.py | 会议预约/取消/查询 | do_login(), do_create_meeting(), do_cancel_meeting(), do_query_meetings(), do_cancel_all_meetings() |
| MeetingControlAW | aw/api/meeting_control_aw.py | 会议控制（等候室等） | do_get_region_info(), do_get_control_token(), do_set_waiting_room() |

---

## 公共 AW

| AW 类 | 文件路径 | 功能概述 | 方法列表 |
|-------|----------|----------|----------|
| CheckAW | aw/common/check_aw.py | 通用检查/等待 | do_check_network(), do_check_version(), do_sleep() |

---

## 基类

| 类名 | 文件路径 | 说明 |
|------|----------|------|
| BaseAW | aw/base_aw.py | UI 操作 AW 基类，提供 ocr_click/ocr_input/ocr_wait 等便捷方法 |
| BaseApiAW | aw/api/base_api_aw.py | API 操作 AW 基类，提供 _get/_post/_delete/_put 等 HTTP 方法 |

---

## 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| 业务方法 | `do_{动作}` | `do_login()` |
| 断言方法 | `should_{期望}` | `should_login_success()` |