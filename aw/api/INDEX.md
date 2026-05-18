# API AW

---

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