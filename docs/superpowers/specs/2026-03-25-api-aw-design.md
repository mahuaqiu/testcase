# API AW 模块设计文档

## 一、概述

### 1.1 目标

为提升测试用例执行速度，新增 API AW 模块，通过直接调用华为云会议 HTTP API 完成会前操作（预约会议、取消会议等），避免不必要的 UI 操作。

### 1.2 使用场景

- 用例需要预约会议作为前置条件 → API 预约，无需打开页面
- 用例结束后需要清理会议 → API 取消，快速清理
- 会控接口控制（会议中操作）→ 后续扩展

### 1.3 设计原则

1. **跨平台共享**：API AW 不绑定特定平台，所有平台用例都可使用
2. **实例隔离**：`users["userA"]`（UI）和 `users["userA_api"]`（API）使用同一账号但独立 token
3. **与现有架构一致**：遵循 AW 层命名规范，集成 ReportLogger

---

## 二、架构设计

### 2.1 目录结构

```
aw/api/
├── __init__.py
├── base_api_aw.py         # API AW 基类
└── meeting_manage_aw.py    # 会议管理 API

variable/
├── manage_var.py          # 会议管理 URL 常量
└── ...
```

### 2.2 组件关系

```
┌─────────────────────────────────────────────────────────┐
│                      测试用例                            │
│  users["userA"] (UI)    users["userA_api"] (API)       │
│        │                        │                        │
│        ▼                        ▼                        │
│  ┌─────────────┐         ┌──────────────────┐           │
│  │  LoginAW    │         │ MeetingManageAW  │           │
│  │  (Web UI)   │         │   (API)          │           │
│  └─────────────┘         └──────────────────┘           │
│        │                        │                        │
│        ▼                        ▼                        │
│  TestagentClient          BaseApiAW                     │
│  (UI 操作)                (HTTP 请求)                    │
└─────────────────────────────────────────────────────────┘
```

---

## 三、组件详细设计

### 3.1 BaseApiAW（API AW 基类）

**职责**：提供 HTTP 请求封装、Token 管理、日志记录

**位置**：`aw/api/base_api_aw.py`

**关键属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `user` | User | 用户资源实例 |
| `_token` | str | 缓存的 access token |
| `_token_expire_time` | float | token 过期时间戳 |

**关键方法**：

| 方法 | 说明 |
|------|------|
| `_request(method, url, **kwargs)` | 发送 HTTP 请求，自动带上 token |
| `_login()` | 登录获取 token（内部方法） |
| `_ensure_token()` | 确保 token 有效，过期则重新登录 |
| `_get(method, endpoint, params)` | GET 请求 |
| `_post(method, endpoint, data)` | POST 请求 |
| `_delete(method, endpoint, params)` | DELETE 请求 |

**Token 管理逻辑**：

```
调用 API 方法
    │
    ▼
_ensure_token()
    │
    ├─ token 存在且未过期 → 直接使用
    │
    └─ token 不存在或已过期 → _login() 获取新 token
                                    │
                                    ▼
                           缓存 token + 过期时间
```

**日志集成**：

复用 `ReportLogger.log_aw_call()` 记录 API 调用日志，与 UI AW 保持一致。

---

### 3.2 MeetingManageAW（会议管理 API）

**职责**：封装会议管理相关 API 操作

**位置**：`aw/api/meeting_manage_aw.py`

**方法列表**：

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `do_login()` | 显式登录获取 token | None |
| `do_create_meeting(subject, start_time, length=60, ...)` | 预约/创建会议 | `MeetingInfo` |
| `do_cancel_meeting(conference_id)` | 取消指定会议 | None |
| `do_query_meetings()` | 查询我的会议列表 | `List[MeetingInfo]` |
| `do_cancel_all_meetings()` | 取消所有会议 | None |

**返回值结构**：

```python
@dataclass
class MeetingInfo:
    """会议信息。"""
    conference_id: str        # 会议 ID
    chair_pwd: str           # 主持人密码
    guest_pwd: str           # 来宾密码
    chair_join_uri: str      # 主持人入会链接
    guest_join_uri: str      # 与会者入会链接
    subject: str             # 会议主题
    start_time: str          # 开始时间
    end_time: str            # 结束时间
```

**创建会议参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `subject` | str | 是 | - | 会议主题 |
| `start_time` | str | 否 | 当前时间+5分钟 | 开始时间，格式 "YYYY-MM-DD HH:MM" |
| `length` | int | 否 | 60 | 会议时长（分钟） |
| `guest_pwd` | str | 否 | 自动生成 | 来宾密码 |

---

### 3.3 用户资源管理器修改

**修改文件**：`conftest.py` 或 `common/user_manager.py`

**新增功能**：支持 `_api` 后缀自动映射

**映射规则**：

```
users["userA"]      → User 实例 (platform="web", 独立 token 存储)
users["userA_api"]  → User 实例 (platform="api", 同一账号密码)
```

**实现方式**：

1. 在 `users` fixture 中检测 `user_id` 是否以 `_api` 结尾
2. 如果是，提取基础 user_id（如 `userA_api` → `userA`）
3. 使用基础 user_id 申请资源，但创建独立的 User 实例
4. User 实例标记 `platform="api"`，用于区分

**示例**：

```python
# 测试用例中
@pytest.mark.users({"userA": "web"})
class TestMeetingCreate:
    def test_execute(self, users):
        # UI 操作
        user_ui = users["userA"]
        login_aw = LoginAW(client, user=user_ui)
        login_aw.do_login()

        # API 操作（同一账号，独立 token）
        user_api = users["userA_api"]  # 自动映射
        api_aw = MeetingManageAW(user=user_api)
        meeting = api_aw.do_create_meeting("测试会议")
```

---

### 3.4 variable/manage_var.py

**职责**：定义会议管理相关 URL 常量

**内容**：

```python
"""会议管理 API URL 常量。"""


class ManageVar:
    """会议管理 API 常量。"""

    # 基础 URL
    BASE_URL = "https://meeting.huaweicloud.com"

    # 登录接口
    LOGIN_URL = f"{BASE_URL}/v2/usg/acs/auth/account"

    # 会议管理接口
    CONFERENCE_URL = f"{BASE_URL}/v1/mmc/management/conferences"
```

---

## 四、API 接口说明

### 4.1 登录接口

- **URL**: `POST /v2/usg/acs/auth/account?ts={timestamp}`
- **Headers**:
  - `Authorization`: `Basic {base64(account:password)}`
  - `Content-Type`: `application/json`
- **Body**:
  ```json
  {"account": "手机号", "clientType": 0, "createTokenType": 0}
  ```
- **Response**:
  ```json
  {"accessToken": "xxx", "validPeriod": 65404, ...}
  ```

### 4.2 创建会议

- **URL**: `POST /v1/mmc/management/conferences?ts={timestamp}`
- **Headers**:
  - `x-auth-token`: `{token}`
  - `x-access-token`: `{token}`
  - `Content-Type`: `application/json`
- **Body**: 会议配置 JSON（见需求文档）
- **Response**: 会议信息列表

### 4.3 取消会议

- **URL**: `DELETE /v1/mmc/management/conferences?ts={timestamp}&conferenceID={id}`
- **Headers**:
  - `x-auth-token`: `{token}`
  - `x-access-token`: `{token}`

### 4.4 查询会议列表

- **URL**: `GET /v1/mmc/management/conferences?ts={timestamp}&userUUID={uuid}&offset=0&limit=10&queryAll=false&searchKey=&queryConfMode=ALL`
- **Headers**:
  - `x-auth-token`: `{token}`
  - `x-access-token`: `{token}`
- **Response**: 会议列表 JSON

---

## 五、使用示例

### 5.1 基本使用

```python
@pytest.mark.users({"userA": "web"})
class TestMeetingScenario:
    def test_execute(self, users):
        user_ui = users["userA"]
        user_api = users["userA_api"]

        # API 预约会议
        api_aw = MeetingManageAW(user=user_api)
        meeting = api_aw.do_create_meeting("自动化测试会议")

        # UI 加入会议
        client = TestagentClient()
        login_aw = LoginAW(client, user=user_ui)
        login_aw.do_login()
        # ... 使用 meeting.guest_join_uri 入会

        # API 取消会议
        api_aw.do_cancel_meeting(meeting.conference_id)
```

### 5.2 清理所有会议

```python
def teardown(self, users):
    user_api = users["userA_api"]
    api_aw = MeetingManageAW(user=user_api)
    api_aw.do_cancel_all_meetings()
```

---

## 六、测试要点

1. **Token 自动刷新**：模拟 token 过期，验证自动重新登录
2. **实例隔离**：同时使用 `userA` 和 `userA_api`，验证 token 不互相覆盖
3. **日志记录**：验证 API 调用被正确记录到报告
4. **错误处理**：模拟网络错误、API 返回错误，验证异常处理

---

## 七、扩展计划

1. **会议控制 API**：`aw/api/meeting_control_aw.py`（后续实现）
2. **更多会议配置参数**：支持完整会议配置选项
3. **并发安全**：如需要，添加全局 Token 管理器支持并发