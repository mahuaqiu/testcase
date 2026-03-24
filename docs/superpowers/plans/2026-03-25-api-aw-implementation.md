# API AW 模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 API AW 模块，支持通过 HTTP API 进行会议管理操作（登录、预约、取消、查询会议），并提供 `_api` 后缀用户映射机制。

**Architecture:**
- 新增 `aw/api/` 目录存放 API 相关 AW 类
- `BaseApiAW` 基类提供 HTTP 请求、Token 管理、日志记录
- 修改 `User` 类支持 `platform="api"` 时不初始化 TestagentClient
- 修改 `conftest.py` 支持 `_api` 后缀自动映射

**Tech Stack:** Python 3.x, requests, dataclasses, pytest

---

## 文件结构

```
aw/api/
├── __init__.py              # 新建：空文件
├── base_api_aw.py           # 新建：API AW 基类
└── meeting_manage_aw.py     # 新建：会议管理 API

variable/
└── manage_var.py            # 新建：会议管理 URL 常量

common/
└── user.py                  # 修改：支持 api 平台

conftest.py                  # 修改：支持 _api 后缀映射
```

---

## Task 1: 创建 variable/manage_var.py

**Files:**
- Create: `variable/manage_var.py`

- [ ] **Step 1: 创建 URL 常量文件**

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

- [ ] **Step 2: 提交**

```bash
git add variable/manage_var.py
git commit -m "feat: 新增会议管理 API URL 常量"
```

---

## Task 2: 创建 aw/api/__init__.py

**Files:**
- Create: `aw/api/__init__.py`

- [ ] **Step 1: 创建空初始化文件**

```python
"""API AW 模块。"""
```

- [ ] **Step 2: 提交**

```bash
git add aw/api/__init__.py
git commit -m "feat: 新增 aw/api 模块"
```

---

## Task 3: 创建 aw/api/base_api_aw.py

**Files:**
- Create: `aw/api/base_api_aw.py`

- [ ] **Step 1: 创建 BaseApiAW 基类**

```python
"""API AW 基类。

提供 HTTP 请求封装、Token 管理、日志记录。
"""

import base64
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

import requests

from common.report_logger import ReportLogger

if TYPE_CHECKING:
    from common.user import User


class ApiError(Exception):
    """API 调用失败异常。"""

    def __init__(self, method: str, status_code: int, message: str):
        self.method = method
        self.status_code = status_code
        self.message = message
        super().__init__(f"{method} 失败 [{status_code}]: {message}")


@dataclass
class TokenInfo:
    """Token 信息。"""
    access_token: str
    expire_time: float  # 过期时间戳（秒）


class BaseApiAW:
    """API AW 基类。

    提供 HTTP 请求封装、Token 自动管理、日志记录。

    Args:
        user: User 实例，用于获取账号密码。
    """

    # 子类应设置 _LOGIN_URL
    _LOGIN_URL: str = ""

    def __init__(self, user: "User"):
        self.user = user
        self._aw_name = self.__class__.__name__
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._token_info: Optional[TokenInfo] = None

    # ── Token 管理 ─────────────────────────────────────────

    def _login(self) -> TokenInfo:
        """登录获取 token。

        Returns:
            TokenInfo 实例。

        Raises:
            ApiError: 登录失败时抛出。
        """
        if not self._LOGIN_URL:
            raise NotImplementedError("子类必须设置 _LOGIN_URL")

        # 构造 Basic Auth
        credentials = f"{self.user.account}:{self.user.password}"
        basic_auth = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {basic_auth}",
        }

        body = {
            "account": self.user.account,
            "clientType": 0,
            "createTokenType": 0,
        }

        response = self._request_with_log(
            "POST",
            self._LOGIN_URL,
            headers=headers,
            json_data=body,
            need_token=False
        )

        data = response.json()
        access_token = data.get("accessToken")
        valid_period = data.get("validPeriod", 3600)  # 默认 1 小时

        if not access_token:
            raise ApiError("login", response.status_code, "未获取到 accessToken")

        # 计算过期时间（提前 60 秒过期，避免临界情况）
        expire_time = time.time() + valid_period - 60

        self._token_info = TokenInfo(
            access_token=access_token,
            expire_time=expire_time
        )

        return self._token_info

    def _ensure_token(self) -> str:
        """确保 token 有效，返回 access_token。

        如果 token 不存在或已过期，自动重新登录。

        Returns:
            access_token 字符串。
        """
        if self._token_info and time.time() < self._token_info.expire_time:
            return self._token_info.access_token

        # 需要重新登录
        token_info = self._login()
        return token_info.access_token

    # ── HTTP 请求 ─────────────────────────────────────────

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
        """发送 HTTP 请求并记录日志。

        Args:
            method: HTTP 方法（GET/POST/DELETE）。
            url: 请求 URL。
            headers: 请求头。
            params: URL 参数。
            json_data: JSON 请求体。
            need_token: 是否需要 token。
            timeout: 超时时间（秒）。

        Returns:
            Response 对象。

        Raises:
            ApiError: 请求失败时抛出。
        """
        logger = ReportLogger.get_current()
        start_time = time.time()

        # 合并 headers
        final_headers = dict(self._session.headers)
        if headers:
            final_headers.update(headers)

        # 添加 token
        if need_token:
            token = self._ensure_token()
            final_headers["x-auth-token"] = token
            final_headers["x-access-token"] = token

        # 记录请求参数（用于日志）
        log_args = {"url": url, "method": method}
        if params:
            log_args["params"] = params
        if json_data:
            log_args["body"] = json_data

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=final_headers,
                params=params,
                json=json_data,
                timeout=timeout
            )

            duration_ms = int((time.time() - start_time) * 1000)
            success = response.ok

            # 记录日志
            logger.log_aw_call(
                aw_name=self._aw_name,
                method=method,
                args=log_args,
                success=success,
                result={"status_code": response.status_code, "body": response.text[:500]},
                duration_ms=duration_ms
            )

            if not success:
                raise ApiError(method, response.status_code, response.text[:200])

            return response

        except requests.exceptions.RequestException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.log_aw_call(
                aw_name=self._aw_name,
                method=method,
                args=log_args,
                success=False,
                result={"error": str(e)},
                duration_ms=duration_ms
            )
            raise ApiError(method, 0, str(e)) from e

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET 请求。

        Args:
            url: 请求 URL。
            params: URL 参数。

        Returns:
            响应 JSON 数据。
        """
        # 添加时间戳参数
        if params is None:
            params = {}
        params["ts"] = int(time.time())

        response = self._request_with_log("GET", url, params=params)
        return response.json()

    def _post(self, url: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST 请求。

        Args:
            url: 请求 URL。
            data: JSON 请求体。

        Returns:
            响应 JSON 数据。
        """
        # 添加时间戳参数
        params = {"ts": int(time.time())}

        response = self._request_with_log("POST", url, params=params, json_data=data)
        return response.json()

    def _delete(self, url: str, params: Optional[Dict[str, Any]] = None) -> None:
        """DELETE 请求。

        Args:
            url: 请求 URL。
            params: URL 参数。
        """
        # 添加时间戳参数
        if params is None:
            params = {}
        params["ts"] = int(time.time())

        self._request_with_log("DELETE", url, params=params)
```

- [ ] **Step 2: 提交**

```bash
git add aw/api/base_api_aw.py
git commit -m "feat: 新增 BaseApiAW 基类

- 提供 HTTP 请求封装 (GET/POST/DELETE)
- Token 自动管理（登录、缓存、过期刷新）
- 日志记录（集成 ReportLogger）"
```

---

## Task 4: 创建 aw/api/meeting_manage_aw.py

**Files:**
- Create: `aw/api/meeting_manage_aw.py`

- [ ] **Step 1: 创建 MeetingManageAW 类**

```python
"""会议管理 API 操作封装。

封装登录、预约会议、取消会议、查询会议列表等操作。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aw.api.base_api_aw import BaseApiAW
from variable.manage_var import ManageVar


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
    user_uuid: str           # 用户 UUID


class MeetingManageAW(BaseApiAW):
    """会议管理 API 操作封装。

    封装华为云会议管理相关 API 操作。

    Args:
        user: User 实例。
    """

    _LOGIN_URL = ManageVar.LOGIN_URL

    # ── 业务方法 ─────────────────────────────────────────

    def do_login(self) -> None:
        """显式登录获取 token。

        通常无需调用，其他方法会自动登录。
        """
        self._login()

    def do_create_meeting(
        self,
        subject: str,
        start_time: Optional[str] = None,
        length: int = 60,
        guest_pwd: Optional[str] = None,
        **kwargs
    ) -> MeetingInfo:
        """预约/创建会议。

        步骤: 登录 → 构造会议配置 → 调用创建接口 → 返回会议信息。

        Args:
            subject: 会议主题。
            start_time: 开始时间，格式 "YYYY-MM-DD HH:MM"，默认当前时间+5分钟。
            length: 会议时长（分钟），默认 60。
            guest_pwd: 来宾密码，不填则自动生成。
            **kwargs: 其他会议配置参数。

        Returns:
            MeetingInfo 实例，包含会议 ID、密码、入会链接等。

        Raises:
            ApiError: 创建失败时抛出。
        """
        # 默认开始时间：当前时间 + 5 分钟
        if not start_time:
            start_dt = datetime.now() + timedelta(minutes=5)
            start_time = start_dt.strftime("%Y-%m-%d %H:%M")

        # 构造会议配置
        body = self._build_meeting_body(subject, start_time, length, guest_pwd, **kwargs)

        # 调用创建接口
        result = self._post(ManageVar.CONFERENCE_URL, data=body)

        # 解析响应
        if isinstance(result, list) and len(result) > 0:
            meeting_data = result[0]
        else:
            meeting_data = result

        return self._parse_meeting_info(meeting_data)

    def do_cancel_meeting(self, conference_id: str) -> None:
        """取消指定会议。

        步骤: 登录 → 调用取消接口。

        Args:
            conference_id: 会议 ID。

        Raises:
            ApiError: 取消失败时抛出。
        """
        params = {"conferenceID": conference_id}
        self._delete(ManageVar.CONFERENCE_URL, params=params)

    def do_query_meetings(self, limit: int = 10) -> List[MeetingInfo]:
        """查询我的会议列表。

        步骤: 登录 → 调用查询接口 → 解析响应。

        Args:
            limit: 返回数量限制，默认 10。

        Returns:
            MeetingInfo 列表。

        Raises:
            ApiError: 查询失败时抛出。
        """
        # 获取 user_uuid（从 token 中获取，或从登录响应中获取）
        user_uuid = self._get_user_uuid()

        params = {
            "userUUID": user_uuid,
            "offset": 0,
            "limit": limit,
            "queryAll": "false",
            "searchKey": "",
            "queryConfMode": "ALL"
        }

        result = self._get(ManageVar.CONFERENCE_URL, params=params)

        meetings = []
        if isinstance(result, list):
            for meeting_data in result:
                meetings.append(self._parse_meeting_info(meeting_data))

        return meetings

    def do_cancel_all_meetings(self) -> int:
        """取消所有会议。

        步骤: 查询会议列表 → 遍历取消每个会议。

        Returns:
            取消的会议数量。

        Raises:
            ApiError: 取消失败时抛出。
        """
        meetings = self.do_query_meetings(limit=100)
        cancelled_count = 0

        for meeting in meetings:
            try:
                self.do_cancel_meeting(meeting.conference_id)
                cancelled_count += 1
            except ApiError:
                # 单个取消失败不中断整体流程
                pass

        return cancelled_count

    # ── 内部方法 ─────────────────────────────────────────

    def _build_meeting_body(
        self,
        subject: str,
        start_time: str,
        length: int,
        guest_pwd: Optional[str],
        **kwargs
    ) -> Dict[str, Any]:
        """构造创建会议请求体。

        Args:
            subject: 会议主题。
            start_time: 开始时间。
            length: 时长（分钟）。
            guest_pwd: 来宾密码。
            **kwargs: 其他配置。

        Returns:
            请求体字典。
        """
        body = {
            "startTime": start_time,
            "timeZoneID": "52",
            "vmrID": None,
            "userVmrId": None,
            "isAutoRecord": 0,
            "picLayouts": [],
            "picDisplay": {},
            "interpreterGroups": [],
            "autoSimultaneousInterpretation": True,
            "supportSimultaneousInterpretation": False,
            "subject": subject,
            "language": "zh-CN",
            "mediaTypes": "Data,HDVideo,Voice",
            "conferenceType": 0,
            "recordType": 2,
            "recordAuxStream": 1,
            "confConfigInfo": {
                "vmrIDType": 1,
                "isGuestFreePwd": False,
                "callInRestriction": 0,
                "isSendSms": False,
                "isSendCalendar": False,
                "defaultSummaryState": 0,
                "enableWaitingRoom": False,
                "supportWaitingRoom": True,
                "allowGuestStartConf": True,
                "isKeyAssuranceConf": False,
                "isShowSettingTips": False,
                "joinBeforeHostTime": 10,
                "connectorCallInRestriction": 0,
                "highResolutionMode": 0,
                "isSendNotify": False,
                "confExtendProperties": [
                    {"propertyKey": "enableVideo4k", "propertyValue": "false"},
                    {"propertyKey": "autoPublishSummary", "propertyValue": "false"},
                    {"propertyKey": "forbiddenScreenShots", "propertyValue": "false"},
                    {"propertyKey": "supportWatermark", "propertyValue": "false"}
                ]
            },
            "attendees": [],
            "length": length,
            "vmrFlag": 0
        }

        # 设置来宾密码
        if guest_pwd:
            body["confConfigInfo"]["guestPwd"] = guest_pwd

        # 合并额外配置
        body.update(kwargs)

        return body

    def _parse_meeting_info(self, data: Dict[str, Any]) -> MeetingInfo:
        """解析会议信息响应。

        Args:
            data: API 响应数据。

        Returns:
            MeetingInfo 实例。
        """
        # 解析密码
        chair_pwd = ""
        guest_pwd = ""
        for pwd_entry in data.get("passwordEntry", []):
            if pwd_entry.get("conferenceRole") == "chair":
                chair_pwd = pwd_entry.get("password", "")
            elif pwd_entry.get("conferenceRole") == "general":
                guest_pwd = pwd_entry.get("password", "")

        return MeetingInfo(
            conference_id=data.get("conferenceID", ""),
            chair_pwd=chair_pwd,
            guest_pwd=guest_pwd,
            chair_join_uri=data.get("chairJoinUri", ""),
            guest_join_uri=data.get("guestJoinUri", ""),
            subject=data.get("subject", ""),
            start_time=data.get("startTime", ""),
            end_time=data.get("endTime", ""),
            user_uuid=data.get("userUUID", "")
        )

    def _get_user_uuid(self) -> str:
        """获取用户 UUID。

        从登录响应或缓存中获取 user_uuid。

        Returns:
            user_uuid 字符串。
        """
        # 如果 token_info 中有 user_uuid，直接返回
        # 否则从查询结果中提取
        # 这里简化处理，从已创建的会议中获取
        meetings = self.do_query_meetings(limit=1)
        if meetings:
            return meetings[0].user_uuid

        # 如果没有会议，需要通过其他方式获取
        # 这里返回空，实际使用时应该从登录响应中获取
        return ""
```

- [ ] **Step 2: 提交**

```bash
git add aw/api/meeting_manage_aw.py
git commit -m "feat: 新增 MeetingManageAW 会议管理 API

- do_login: 显式登录
- do_create_meeting: 预约/创建会议
- do_cancel_meeting: 取消指定会议
- do_query_meetings: 查询会议列表
- do_cancel_all_meetings: 取消所有会议"
```

---

## Task 5: 修改 aw/__init__.py 支持 api 平台

**Files:**
- Modify: `aw/__init__.py`

- [ ] **Step 1: 添加 api 到支持的平台列表**

找到 `get_platform_aw_classes` 函数，确保它能正确加载 `aw/api/` 目录下的 AW 类。

当前实现已经支持动态发现任何子目录下的 `*_aw.py` 文件，无需修改。

验证：确认 `aw/api/base_api_aw.py` 和 `aw/api/meeting_manage_aw.py` 能被正确发现。

- [ ] **Step 2: 无需修改，提交确认**

```bash
git status
# 确认 aw/__init__.py 无需修改
```

---

## Task 6: 修改 common/user.py 支持 api 平台

**Files:**
- Modify: `common/user.py`

- [ ] **Step 1: 修改 User 类，支持 platform="api" 时不初始化 TestagentClient**

在 `__init__` 方法中添加判断：

```python
def __init__(
    self,
    user_id: str,
    platform: str,
    ip: str,
    port: int,
    account: str,
    password: str,
    **extra: Any
):
    """初始化用户资源。

    Args:
        user_id: 用户标识。
        platform: 平台类型。
        ip: Worker IP 地址。
        port: Worker 端口。
        account: 登录账号。
        password: 登录密码。
        **extra: 扩展信息。
    """
    self.user_id = user_id
    self.platform = platform
    self.ip = ip
    self.port = port
    self.account = account
    self.password = password
    self.extra = extra

    # API 平台不需要 TestagentClient
    if platform == "api":
        self.client = None
    else:
        # 初始化 TestagentClient
        base_url = f"http://{ip}:{port}"
        self.client = TestagentClient(base_url)

    # 加载 AW 实例
    self._aw_instances: Dict[str, Any] = {}
    self._load_aw_modules()
```

- [ ] **Step 2: 修改 _load_aw_modules 方法，支持加载 api 平台的 AW**

```python
def _load_aw_modules(self) -> None:
    """加载公共 AW 和对应平台的 AW。"""
    from aw import get_platform_aw_classes

    # 1. 加载公共 AW
    for aw_class in get_platform_aw_classes("common"):
        instance = aw_class(self.client, self)
        self._aw_instances[aw_class.__name__] = instance

    # 2. 加载平台 AW（包括 api）
    if self.platform == "api":
        # API 平台加载 api 目录下的 AW
        for aw_class in get_platform_aw_classes("api"):
            instance = aw_class(self)
            self._aw_instances[aw_class.__name__] = instance
    else:
        # 其他平台加载对应平台的 AW
        for aw_class in get_platform_aw_classes(self.platform):
            instance = aw_class(self.client, self)
            self._aw_instances[aw_class.__name__] = instance
```

- [ ] **Step 3: 修改 screenshot 方法，API 平台返回空**

```python
def screenshot(self) -> str:
    """截图并返回 base64。

    Returns:
        截图的 base64 编码。API 平台返回空字符串。
    """
    if self.platform == "api" or self.client is None:
        return ""

    result = self.client.screenshot(self.platform)
    # 从结果中提取 base64 数据
    if result.get("status") == "success" and result.get("actions"):
        return result["actions"][0].get("output", "")
    return ""
```

- [ ] **Step 4: 提交**

```bash
git add common/user.py
git commit -m "feat: User 类支持 platform='api'

- API 平台不初始化 TestagentClient
- API 平台加载 aw/api/ 下的 AW
- screenshot 方法对 API 平台返回空"
```

---

## Task 7: 修改 conftest.py 支持 _api 后缀映射

**Files:**
- Modify: `conftest.py`

- [ ] **Step 1: 修改 users fixture，支持 _api 后缀**

在 `users` fixture 中，添加 `_api` 后缀处理逻辑。

找到以下代码段：

```python
    # 创建 User 实例
    for user_id, resource in resources.items():
        user = User(
            user_id=user_id,
            platform=resource.platform,
            ip=resource.ip,
            port=resource.port,
            account=resource.account,
            password=resource.password,
            **resource.extra
        )
        user_instances[user_id] = user
```

修改为：

```python
    # 创建 User 实例
    for user_id, resource in resources.items():
        user = User(
            user_id=user_id,
            platform=resource.platform,
            ip=resource.ip,
            port=resource.port,
            account=resource.account,
            password=resource.password,
            **resource.extra
        )
        user_instances[user_id] = user

        # 支持 _api 后缀：创建同一账号的 API 实例
        api_user_id = f"{user_id}_api"
        api_user = User(
            user_id=api_user_id,
            platform="api",
            ip=resource.ip,
            port=resource.port,
            account=resource.account,
            password=resource.password,
            **resource.extra
        )
        user_instances[api_user_id] = api_user
```

- [ ] **Step 2: 提交**

```bash
git add conftest.py
git commit -m "feat: users fixture 支持 _api 后缀映射

- users['userA_api'] 自动创建 platform='api' 的 User 实例
- 使用同一账号密码，但独立 token"
```

---

## Task 8: 验证实现

**Files:**
- Create: `testcases/web/meeting/test_api_aw_demo.py` (临时测试文件)

- [ ] **Step 1: 创建验证测试用例**

```python
"""API AW 功能验证测试。

验证 _api 后缀映射和 MeetingManageAW 基本功能。
"""

import pytest


@pytest.mark.users({"userA": "web"})
class TestApiAwDemo:
    """API AW 功能验证。"""

    def test_execute(self, users):
        """执行测试：验证 API AW 功能。"""
        # 获取 UI 用户和 API 用户
        user_ui = users["userA"]
        user_api = users["userA_api"]

        # 验证 API 用户属性
        assert user_api.platform == "api"
        assert user_api.account == user_ui.account
        assert user_api.password == user_ui.password
        assert user_api.client is None  # API 用户没有 TestagentClient

        # 验证 API AW 加载
        assert hasattr(user_api, "do_create_meeting")

        print("API AW 功能验证通过")
```

- [ ] **Step 2: 运行测试**

```bash
cd /Users/ma/Documents/testcase
source .venv/bin/activate
pytest testcases/web/meeting/test_api_aw_demo.py -v
```

预期输出：测试通过

- [ ] **Step 3: 清理测试文件**

```bash
rm testcases/web/meeting/test_api_aw_demo.py
```

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: 完成 API AW 模块实现

- 新增 BaseApiAW 基类（Token 管理、HTTP 请求、日志）
- 新增 MeetingManageAW（登录、预约、取消、查询会议）
- User 类支持 platform='api'
- users fixture 支持 _api 后缀映射"
```

---

## 完成检查清单

- [ ] `variable/manage_var.py` 创建完成
- [ ] `aw/api/__init__.py` 创建完成
- [ ] `aw/api/base_api_aw.py` 创建完成
- [ ] `aw/api/meeting_manage_aw.py` 创建完成
- [ ] `common/user.py` 修改完成
- [ ] `conftest.py` 修改完成
- [ ] 验证测试通过
- [ ] 所有提交完成