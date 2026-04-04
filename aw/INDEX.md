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

### CheckAW

> 文件路径：`aw/common/check_aw.py`
> 功能概述：公共检查操作封装（暂无方法）

---

## 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| 业务方法 | `do_{动作}` | `do_login()` |
| 断言方法 | `should_{期望}` | `should_login_success()` |