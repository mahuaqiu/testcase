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

variable/
└── manage_var.py             # URL 常量（已存在，需新增会议控制相关 URL）
```

## URL 常量设计

在 `variable/manage_var.py` 中新增会议控制相关 URL：

```python
class ManageVar:
    """会议管理 API 常量。"""

    # 基础 URL
    BASE_URL = "https://meeting.huaweicloud.com"  # 已存在

    # 登录接口
    LOGIN_URL = f"{BASE_URL}/v2/usg/acs/auth/account"  # 已存在

    # 会议管理接口
    CONFERENCE_URL = f"{BASE_URL}/v1/mmc/management/conferences"  # 已存在

    # 会议站点信息接口
    REGION_INFO_URL = f"{BASE_URL}/v1/mmc/management/conferences/region/random"  # 新增
```

**会议控制接口 URL**（动态拼接）：
- Token 接口：`https://{region_ip}/v1/mmc/control/conferences/token`
- 配置更新接口：`https://{region_ip}/v1/mmc/control/conferences/updateStartedConfConfig`

> 区域服务器地址（region_ip）通过 `do_get_region_info` 动态获取，因此会议控制接口 URL 需要运行时拼接。

## 数据结构

### RegionInfo

```python
@dataclass
class RegionInfo:
    """会议站点信息。"""
    region_ip: str    # 区域服务器地址
    uuid: str         # 会议 UUID
```

**API 响应结构**：
```json
{
    "regionIP": "r2.meeting.huaweicloud.com",
    "uuid": "cnr79d05d39bb6b4375aeecdd823c37639d68fb87efe95c306f"
}
```

**解析逻辑**：
```python
def _parse_region_info(self, data: Dict[str, Any]) -> RegionInfo:
    """解析站点信息响应。"""
    return RegionInfo(
        region_ip=data.get("regionIP", ""),
        uuid=data.get("uuid", "")
    )
```

## 方法设计

### 业务方法总览

| 方法 | 说明 | HTTP 方法 | 认证方式 |
|------|------|-----------|----------|
| `do_get_region_info(conference_id)` | 获取会议站点信息 | GET | x-auth-token / x-access-token |
| `do_get_control_token(conference_id, chair_password)` | 获取会议控制 token | POST | X-Password + x-login-type |
| `do_set_waiting_room(conference_id, chair_password, enable)` | 设置等候室开关 | PUT | x-conference-authorization |

### do_get_region_info

```python
def do_get_region_info(self, conference_id: str) -> RegionInfo:
    """获取会议站点信息。

    步骤: 使用登录 token 调用站点信息接口 → 返回区域服务器地址。

    Args:
        conference_id: 会议 ID。

    Returns:
        RegionInfo 实例，包含区域服务器地址和 UUID。

    Raises:
        ApiError: 请求失败或响应数据异常时抛出。
    """
```

**API 调用**：
- URL: `ManageVar.REGION_INFO_URL`
- Method: GET
- Headers: `x-auth-token`, `x-access-token`（复用登录 token）
- Params: `ts`, `conferenceID`

**缓存检查**：调用前检查 `_region_info_cache`，命中则直接返回。

### do_get_control_token

```python
def do_get_control_token(self, conference_id: str, chair_password: str) -> str:
    """获取会议控制 token。

    步骤: 获取站点信息 → 调用 token 接口 → 返回控制 token。

    Args:
        conference_id: 会议 ID。
        chair_password: 主持人密码。

    Returns:
        会议控制 token 字符串。

    Raises:
        ApiError: 请求失败或响应数据异常时抛出。
    """
```

**API 调用**：
- URL: `https://{region_ip}/v1/mmc/control/conferences/token`
- Method: POST
- Headers: `x-login-type: 1`, `X-Password: {chair_password}`, `Content-Type: application/json`
- Params: `conferenceID`

**响应结构**：
```json
{
    "data": {
        "token": "cnr8dcd159750bf9e72cdeb5960f11e0166624ce152ddee265e",
        "tmpWsToken": "...",
        "wsURL": "...",
        "role": 1,
        "expireTime": 1774448090909
    }
}
```

**解析逻辑**：从 `response["data"]["token"]` 获取 token 字符串。

**缓存检查**：调用前检查 `_control_token_cache`，命中则直接返回。

### do_set_waiting_room

```python
def do_set_waiting_room(self, conference_id: str, chair_password: str, enable: bool) -> None:
    """设置等候室开关。

    步骤: 获取控制 token → 调用配置更新接口。

    Args:
        conference_id: 会议 ID。
        chair_password: 主持人密码。
        enable: True 开启等候室，False 关闭。

    Raises:
        ApiError: 请求失败时抛出。
    """
```

**API 调用**：
- URL: `https://{region_ip}/v1/mmc/control/conferences/updateStartedConfConfig`
- Method: PUT
- Headers: `x-conference-authorization: Basic {token}`, `Content-Type: application/json`
- Params: `conferenceID`
- Body: `{"enableWaitingRoom": 1}` 或 `{"enableWaitingRoom": 0}`

## 内部实现

### 缓存策略

```python
self._region_info_cache: Dict[str, RegionInfo] = {}
self._control_token_cache: Dict[str, str] = {}
```

**缓存使用场景**：
- 同一测试用例中多次调用同一会议的控制接口时，避免重复请求

**缓存失效条件**：
- **实例级别缓存**：每个测试用例创建新的 AW 实例，测试结束后实例销毁，缓存自动失效
- **无需显式清理**：会议控制操作通常在同一次测试会话内完成

### 内部方法

#### _get_region_base_url

```python
def _get_region_base_url(self, region_ip: str) -> str:
    """构造区域服务器基础 URL。

    Args:
        region_ip: 区域服务器地址。

    Returns:
        完整的 HTTPS URL。
    """
    return f"https://{region_ip}"
```

#### _parse_region_info

```python
def _parse_region_info(self, data: Dict[str, Any]) -> RegionInfo:
    """解析站点信息响应。

    Args:
        data: API 响应数据。

    Returns:
        RegionInfo 实例。

    Raises:
        ApiError: 关键字段为空时抛出。
    """
    region_ip = data.get("regionIP", "")
    uuid = data.get("uuid", "")

    # 校验关键字段
    if not region_ip:
        raise ApiError("parse_region_info", 0, "响应中缺少 regionIP 字段")
    if not uuid:
        raise ApiError("parse_region_info", 0, "响应中缺少 uuid 字段")

    return RegionInfo(region_ip=region_ip, uuid=uuid)
```

## BaseApiAW 修改

### 修改 _request_with_log 方法签名

为支持会议控制 API 的特殊认证需求，`_request_with_log` 需要支持 `params` 参数透传：

```python
def _request_with_log(
    self,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    need_token: bool = True,
    timeout: int = 30
) -> requests.Response:
```

> 现有实现已支持 `params` 参数，无需修改。

### 新增 _post_with_headers 方法

```python
def _post_with_headers(
    self,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    need_token: bool = True
) -> Dict[str, Any]:
    """带自定义 headers 的 POST 请求。

    Args:
        url: 请求 URL。
        data: JSON 请求体。
        headers: 额外的请求头（可选）。
        params: 额外的查询参数（可选）。
        need_token: 是否需要登录 token，默认 True。

    Returns:
        响应 JSON 数据。

    Raises:
        ApiError: 请求失败时抛出。
    """
    # 合并时间戳和额外参数
    final_params = {"ts": int(time.time())}
    if params:
        final_params.update(params)

    response = self._request_with_log(
        "POST", url,
        params=final_params,
        json_data=data,
        headers=headers,
        need_token=need_token
    )
    return response.json()
```

### 新增 _put 方法

```python
def _put(
    self,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    need_token: bool = True
) -> Dict[str, Any]:
    """PUT 请求。

    Args:
        url: 请求 URL。
        data: JSON 请求体。
        headers: 额外的请求头（可选）。
        params: 额外的查询参数（可选）。
        need_token: 是否需要登录 token，默认 True。

    Returns:
        响应 JSON 数据。

    Raises:
        ApiError: 请求失败时抛出。
    """
    # 合并时间戳和额外参数
    final_params = {"ts": int(time.time())}
    if params:
        final_params.update(params)

    response = self._request_with_log(
        "PUT", url,
        params=final_params,
        json_data=data,
        headers=headers,
        need_token=need_token
    )
    return response.json()
```

> **设计决策**：
> 1. 新增 `_post_with_headers` 而非修改 `_post` 签名，避免影响现有调用方（如 `MeetingManageAW`）
> 2. 方法命名采用 `_post_with_headers` 而非 `_post_with_options`，因为主要差异是支持自定义 headers
> 3. `_put` 是新方法，直接支持完整参数

## 完整类结构

```python
"""会议控制 API 操作封装。

封装等候室控制等会议中操作。
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from aw.api.base_api_aw import ApiError
from aw.api.meeting_manage_aw import MeetingManageAW
from variable.manage_var import ManageVar


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
        client: TestagentClient 实例（API AW 传 None）。
        user: User 实例，用于获取账号密码。
    """

    def __init__(self, client, user):
        """初始化会议控制 AW。

        Args:
            client: TestagentClient 实例（API AW 传 None）。
            user: User 实例。
        """
        super().__init__(client, user)
        self._region_info_cache: Dict[str, RegionInfo] = {}
        self._control_token_cache: Dict[str, str] = {}

    # ── 业务方法 ─────────────────────────────────────────

    def do_get_region_info(self, conference_id: str) -> RegionInfo:
        """获取会议站点信息。

        步骤: 使用登录 token 调用站点信息接口 → 返回区域服务器地址。

        Args:
            conference_id: 会议 ID。

        Returns:
            RegionInfo 实例，包含区域服务器地址和 UUID。

        Raises:
            ApiError: 请求失败或响应数据异常时抛出。
        """
        # 检查缓存
        if conference_id in self._region_info_cache:
            return self._region_info_cache[conference_id]

        # 调用 API
        params = {"conferenceID": conference_id}
        result = self._get(ManageVar.REGION_INFO_URL, params=params)

        # 解析响应
        region_info = self._parse_region_info(result)

        # 缓存结果
        self._region_info_cache[conference_id] = region_info
        return region_info

    def do_get_control_token(self, conference_id: str, chair_password: str) -> str:
        """获取会议控制 token。

        步骤: 获取站点信息 → 调用 token 接口 → 返回控制 token。

        Args:
            conference_id: 会议 ID。
            chair_password: 主持人密码。

        Returns:
            会议控制 token 字符串。

        Raises:
            ApiError: 请求失败或响应数据异常时抛出。
        """
        # 检查缓存
        if conference_id in self._control_token_cache:
            return self._control_token_cache[conference_id]

        # 获取站点信息
        region_info = self.do_get_region_info(conference_id)
        url = f"{self._get_region_base_url(region_info.region_ip)}/v1/mmc/control/conferences/token"

        # 调用 API（使用主持人密码认证，不需要登录 token）
        headers = {
            "x-login-type": "1",
            "X-Password": chair_password
        }
        params = {"conferenceID": conference_id}
        result = self._post_with_headers(url, data=None, headers=headers, params=params, need_token=False)

        # 解析响应
        token = result.get("data", {}).get("token", "")
        if not token:
            raise ApiError("get_control_token", 0, "未获取到控制 token")

        # 缓存结果
        self._control_token_cache[conference_id] = token
        return token

    def do_set_waiting_room(self, conference_id: str, chair_password: str, enable: bool) -> None:
        """设置等候室开关。

        步骤: 获取控制 token → 调用配置更新接口。

        Args:
            conference_id: 会议 ID。
            chair_password: 主持人密码。
            enable: True 开启等候室，False 关闭。

        Raises:
            ApiError: 请求失败时抛出。
        """
        # 获取站点信息和控制 token
        region_info = self.do_get_region_info(conference_id)
        token = self.do_get_control_token(conference_id, chair_password)

        # 构造请求
        url = f"{self._get_region_base_url(region_info.region_ip)}/v1/mmc/control/conferences/updateStartedConfConfig"
        headers = {
            "x-conference-authorization": f"Basic {token}"
        }
        params = {"conferenceID": conference_id}
        body = {"enableWaitingRoom": 1 if enable else 0}

        # 调用 API（使用控制 token 认证，不需要登录 token）
        self._put(url, data=body, headers=headers, params=params, need_token=False)

    # ── 内部方法 ─────────────────────────────────────────

    def _get_region_base_url(self, region_ip: str) -> str:
        """构造区域服务器基础 URL。

        Args:
            region_ip: 区域服务器地址。

        Returns:
            完整的 HTTPS URL。
        """
        return f"https://{region_ip}"

    def _parse_region_info(self, data: Dict[str, Any]) -> RegionInfo:
        """解析站点信息响应。

        Args:
            data: API 响应数据。

        Returns:
            RegionInfo 实例。

        Raises:
            ApiError: 关键字段为空时抛出。
        """
        region_ip = data.get("regionIP", "")
        uuid = data.get("uuid", "")

        if not region_ip:
            raise ApiError("parse_region_info", 0, "响应中缺少 regionIP 字段")
        if not uuid:
            raise ApiError("parse_region_info", 0, "响应中缺少 uuid 字段")

        return RegionInfo(region_ip=region_ip, uuid=uuid)
```

## 使用示例

```python
import pytest
from aw.api.meeting_control_aw import MeetingControlAW

# 在测试用例中使用
@pytest.mark.users({"userA": "web"})
class TestWaitingRoom:
    def test_execute(self, users):
        # userA_api 是自动创建的 API 平台用户（与 userA 同账号，独立 token）
        user_api = users["userA_api"]

        # 创建会议控制 AW 实例
        # client 参数传 None（API AW 不需要 TestagentClient）
        control_aw = MeetingControlAW(None, user=user_api)

        # 设置等候室开关
        control_aw.do_set_waiting_room(
            conference_id="960537505",
            chair_password="123456",
            enable=True
        )
```

> **说明**：根据 AGENTS.md 规范，声明 `@pytest.mark.users({"userA": "web"})` 时，fixture 会自动创建两个 User 实例：
> - `users["userA"]`：Web 平台用户，用于 UI 操作
> - `users["userA_api"]`：API 平台用户，用于 API 操作（同一账号，独立 token）

## 实现范围

**本次实现**：
- `RegionInfo` 数据类
- `ManageVar` 新增 `REGION_INFO_URL` 常量
- `BaseApiAW` 新增 `_put()` 和 `_post_with_headers()` 方法
- `MeetingControlAW` 类
  - `do_get_region_info()`
  - `do_get_control_token()`
  - `do_set_waiting_room()`
  - `_get_region_base_url()`
  - `_parse_region_info()`

**后续扩展**：
- 其他会议控制操作（锁定会议、静音全体等）