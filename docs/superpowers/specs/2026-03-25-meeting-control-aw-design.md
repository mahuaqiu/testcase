# 会议控制 AW 设计文档

## 概述

实现 `MeetingControlAW` 类，封装会议控制 API 操作，包括获取会议站点信息、获取会议控制 token、设置等候室开关等功能。

## 架构设计

### 类继承关系

```
MeetingControlAW → MeetingManageAW → BaseApiAW → BaseAW
```

**继承理由**：
- 复用 `MeetingManageAW` 的登录和 token 管理能力
- 共享账号认证体系，代码复用最直接

### 文件结构

```
aw/api/
├── base_api_aw.py           # API AW 基类（已存在，需新增 _put 方法）
├── meeting_manage_aw.py      # 会议管理 AW（已存在）
└── meeting_control_aw.py     # 会议控制 AW（新增）
```

## 数据结构

### RegionInfo

```python
@dataclass
class RegionInfo:
    """会议站点信息。"""
    region_ip: str    # 区域服务器地址
    uuid: str         # 会议 UUID
```

## 方法设计

### 业务方法

| 方法 | 说明 | 认证方式 |
|------|------|----------|
| `do_get_region_info(conference_id)` | 获取会议站点信息 | x-auth-token / x-access-token |
| `do_get_control_token(conference_id, chair_password)` | 获取会议控制 token | X-Password + x-login-type |
| `do_set_waiting_room(conference_id, chair_password, enable)` | 设置等候室开关 | x-conference-authorization |

### 方法详情

#### do_get_region_info

```python
def do_get_region_info(self, conference_id: str) -> RegionInfo:
    """获取会议站点信息。

    步骤: 使用登录 token 调用站点信息接口 → 返回区域服务器地址。

    Args:
        conference_id: 会议 ID。

    Returns:
        RegionInfo 实例，包含区域服务器地址和 UUID。
    """
```

**API 调用**：
- URL: `https://meeting.huaweicloud.com/v1/mmc/management/conferences/region/random`
- Method: GET
- Headers: `x-auth-token`, `x-access-token`（复用登录 token）
- Params: `ts`, `conferenceID`

#### do_get_control_token

```python
def do_get_control_token(self, conference_id: str, chair_password: str) -> str:
    """获取会议控制 token。

    步骤: 获取站点信息 → 调用 token 接口 → 返回控制 token。

    Args:
        conference_id: 会议 ID。
        chair_password: 主持人密码。

    Returns:
        会议控制 token 字符串。
    """
```

**API 调用**：
- URL: `https://{region_ip}/v1/mmc/control/conferences/token`
- Method: POST
- Headers: `x-login-type: 1`, `X-Password: {chair_password}`
- Params: `conferenceID`

**返回值**：响应中 `data.token` 字段

#### do_set_waiting_room

```python
def do_set_waiting_room(self, conference_id: str, chair_password: str, enable: bool) -> None:
    """设置等候室开关。

    步骤: 获取控制 token → 调用配置更新接口。

    Args:
        conference_id: 会议 ID。
        chair_password: 主持人密码。
        enable: True 开启等候室，False 关闭。
    """
```

**API 调用**：
- URL: `https://{region_ip}/v1/mmc/control/conferences/updateStartedConfConfig`
- Method: PUT
- Headers: `x-conference-authorization: Basic {token}`
- Params: `conferenceID`
- Body: `{"enableWaitingRoom": 1}` 或 `{"enableWaitingRoom": 0}`

## 内部实现

### 缓存策略

为避免重复调用，使用实例级缓存：

```python
self._region_info_cache: Dict[str, RegionInfo] = {}
self._control_token_cache: Dict[str, str] = {}
```

### BaseApiAW 修改

新增 `_put` 方法：

```python
def _put(self, url: str, data: Optional[Dict[str, Any]] = None,
         headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """PUT 请求。"""
```

### 认证头处理

会议控制 API 的认证方式与登录 token 不同，需要特殊处理：

1. `do_get_region_info`：复用 `_ensure_token()` 获取的 access_token
2. `do_get_control_token`：使用主持人密码作为 `X-Password` header
3. `do_set_waiting_room`：使用 `Basic {control_token}` 作为 `x-conference-authorization` header

## 完整类结构

```python
"""会议控制 API 操作封装。

封装等候室控制等会议中操作。
"""

from dataclasses import dataclass
from typing import Dict, Optional

from aw.api.meeting_manage_aw import MeetingManageAW


@dataclass
class RegionInfo:
    """会议站点信息。"""
    region_ip: str    # 区域服务器地址
    uuid: str         # 会议 UUID


class MeetingControlAW(MeetingManageAW):
    """会议控制 API 操作封装。

    继承 MeetingManageAW，复用登录和 token 管理。
    提供等候室控制等会议中操作。

    Args:
        user: User 实例。
    """

    # ── 初始化 ─────────────────────────────────────────

    def __init__(self, client, user):
        super().__init__(client, user)
        self._region_info_cache: Dict[str, RegionInfo] = {}
        self._control_token_cache: Dict[str, str] = {}

    # ── 业务方法 ─────────────────────────────────────────

    def do_get_region_info(self, conference_id: str) -> RegionInfo:
        """获取会议站点信息。"""
        ...

    def do_get_control_token(self, conference_id: str, chair_password: str) -> str:
        """获取会议控制 token。"""
        ...

    def do_set_waiting_room(self, conference_id: str, chair_password: str, enable: bool) -> None:
        """设置等候室开关。"""
        ...

    # ── 内部方法 ─────────────────────────────────────────

    def _get_region_base_url(self, region_ip: str) -> str:
        """构造区域服务器基础 URL。"""
        return f"https://{region_ip}"
```

## 依赖修改

### BaseApiAW 新增方法

在 `aw/api/base_api_aw.py` 中新增 `_put` 方法：

```python
def _put(self, url: str, data: Optional[Dict[str, Any]] = None,
         headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """PUT 请求。

    Args:
        url: 请求 URL。
        data: JSON 请求体。
        headers: 额外的请求头。

    Returns:
        响应 JSON 数据。
    """
    params = {"ts": int(time.time())}
    response = self._request_with_log("PUT", url, params=params, json_data=data, headers=headers)
    return response.json()
```

## 使用示例

```python
from aw.api.meeting_control_aw import MeetingControlAW

# 在测试用例中使用
@pytest.mark.users({"userA": "web"})
class TestWaitingRoom:
    def test_execute(self, users):
        user_api = users["userA_api"]

        control_aw = MeetingControlAW(None, user=user_api)
        control_aw.do_set_waiting_room(
            conference_id="960537505",
            chair_password="123456",
            enable=True
        )
```

## 实现范围

**本次实现**：
- `RegionInfo` 数据类
- `MeetingControlAW` 类
  - `do_get_region_info()`
  - `do_get_control_token()`
  - `do_set_waiting_room()`
- `BaseApiAW._put()` 方法

**后续扩展**：
- 其他会议控制操作（锁定会议、静音全体等）