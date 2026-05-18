# Web 平台 AW

---

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