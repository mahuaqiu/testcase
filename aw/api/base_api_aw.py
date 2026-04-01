"""API AW 基类。

提供 HTTP 请求封装、Token 管理、日志记录。
"""

import base64
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

import requests

from aw.base_aw import BaseAW
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
    user_uuid: str = ""  # 用户 UUID


class BaseApiAW(BaseAW):
    """API AW 基类。

    继承 BaseAW 以支持 AW 类发现机制。
    提供 HTTP 请求封装、Token 自动管理、日志记录。

    Args:
        user: User 实例，用于获取账号密码。
    """

    PLATFORM = "api"  # API 平台标识

    # 子类应设置 _LOGIN_URL
    _LOGIN_URL: str = ""

    def __init__(self, client, user: Optional["User"] = None):
        """初始化 API AW。

        Args:
            client: TestagentClient（API AW 不需要，传 None）。
            user: User 实例。
        """
        super().__init__(client, user)
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._token_info: Optional[TokenInfo] = None

    # ── Token 管理 ─────────────────────────────────────────

    def _get_token_from_worker(self) -> Optional[Dict[str, str]]:
        """从 worker 获取 UI User 端已有的 token。

        通过 client.execute 调用 get_token action。

        Returns:
            Token dict 如 {"X-Auth-Token": "xxx"}，或 None。
        """
        logger = ReportLogger.get_current()
        user_id = self.user.user_id if self.user else ""
        user_account = self.user.account if self.user else ""
        user_name = self.user.name if self.user else ""

        client = self.user._get_ui_client()
        if not client:
            logger.log_aw_call(
                aw_name=self._aw_name,
                method="_get_token_from_worker",
                args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                success=False,
                result={"error": "client is None"},
                duration_ms=0
            )
            return None

        ui_platform = self.user._get_ui_platform()
        if not ui_platform:
            logger.log_aw_call(
                aw_name=self._aw_name,
                method="_get_token_from_worker",
                args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                success=False,
                result={"error": "ui_platform is None"},
                duration_ms=0
            )
            return None

        try:
            result = client.execute(
                platform=ui_platform,
                actions=[{"action_type": "get_token"}]
            )

            if result.get("status") == "success" and result.get("actions"):
                output = result["actions"][0].get("output", "")
                if output:
                    try:
                        token_dict = json.loads(output)
                        logger.log_aw_call(
                            aw_name=self._aw_name,
                            method="_get_token_from_worker",
                            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                            success=True,
                            result={"raw_result": result, "token_keys": list(token_dict.keys())},
                            duration_ms=0
                        )
                        return token_dict
                    except json.JSONDecodeError as e:
                        logger.log_aw_call(
                            aw_name=self._aw_name,
                            method="_get_token_from_worker",
                            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                            success=False,
                            result={"raw_result": result, "error": f"JSON parse failed: {e}", "output": output[:100]},
                            duration_ms=0
                        )
                        return None
                else:
                    logger.log_aw_call(
                        aw_name=self._aw_name,
                        method="_get_token_from_worker",
                        args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                        success=False,
                        result={"raw_result": result, "error": "output is empty"},
                        duration_ms=0
                    )
                    return None
            else:
                logger.log_aw_call(
                    aw_name=self._aw_name,
                    method="_get_token_from_worker",
                    args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                    success=False,
                    result={"raw_result": result, "error": "status not success or no actions", "status": result.get("status")},
                    duration_ms=0
                )
                return None
        except Exception as e:
            logger.log_aw_call(
                aw_name=self._aw_name,
                method="_get_token_from_worker",
                args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "ui_user_id": self.user._ui_user_id if self.user else ""},
                success=False,
                result={"error": str(e)},
                duration_ms=0
            )
            return None

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

        # 从登录响应中获取 user_uuid（兼容两种响应格式）
        user_uuid = data.get("userUUID", "")
        if not user_uuid:
            # 尝试从 user.userId 获取
            user_info = data.get("user", {})
            user_uuid = user_info.get("userId", "")

        self._token_info = TokenInfo(
            access_token=access_token,
            expire_time=expire_time,
            user_uuid=user_uuid
        )

        return self._token_info

    def _ensure_token(self) -> str:
        """确保 token 有效，返回 access_token。

        如果 token 不存在或已过期：
        1. 优先尝试从 worker get_token 获取 UI User 的 token
        2. 如果获取成功则直接使用
        3. 如果获取失败则执行原有 API 登录

        Returns:
            access_token 字符串。
        """
        if self._token_info and time.time() < self._token_info.expire_time:
            return self._token_info.access_token

        # 优先尝试从 worker 获取 UI User 的 token
        if self.user and self.user._ui_user_id:
            token_dict = self._get_token_from_worker()
            if token_dict:
                # 使用从 worker 获取的 token
                access_token = token_dict.get("X-Auth-Token")
                if access_token:
                    # 设置一个较短的过期时间（5分钟），因为 UI token 可能随时失效
                    expire_time = time.time() + 300
                    self._token_info = TokenInfo(
                        access_token=access_token,
                        expire_time=expire_time,
                        user_uuid=""
                    )
                    return access_token

        # fallback 到原有 API 登录
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

        # 添加 x-request-id header（随机 UUID）
        final_headers["x-request-id"] = str(uuid.uuid4())

        # 添加 token
        if need_token:
            token = self._ensure_token()
            final_headers["x-auth-token"] = token
            final_headers["x-access-token"] = token

        # 记录请求参数（用于日志）
        log_args = {"url": url, "method": method, "user_id": self.user.user_id if self.user else ""}
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
                timeout=timeout,
                verify=False
            )

            # 401 时尝试从 worker 获取 token 或重新登录
            if response.status_code == 401 and need_token:
                # 清除缓存的 token
                self._token_info = None

                # 尝试从 worker 获取 UI User 的 token
                worker_token = None
                if self.user and self.user._ui_user_id:
                    worker_token = self._get_token_from_worker()

                if worker_token:
                    # 使用 worker token 重试
                    access_token = worker_token.get("X-Auth-Token")
                    if access_token:
                        final_headers["x-auth-token"] = access_token
                        final_headers["x-access-token"] = access_token
                        response = self._session.request(
                            method=method,
                            url=url,
                            headers=final_headers,
                            params=params,
                            json=json_data,
                            timeout=timeout,
                            verify=False
                        )

                        # worker token 也 401，则执行 API login
                        if response.status_code == 401:
                            token = self._ensure_token()
                            final_headers["x-auth-token"] = token
                            final_headers["x-access-token"] = token
                            response = self._session.request(
                                method=method,
                                url=url,
                                headers=final_headers,
                                params=params,
                                json=json_data,
                                timeout=timeout,
                                verify=False
                            )
                    else:
                        # worker_token 没有 X-Auth-Token，执行 API login 重试
                        token = self._ensure_token()
                        final_headers["x-auth-token"] = token
                        final_headers["x-access-token"] = token
                        response = self._session.request(
                            method=method,
                            url=url,
                            headers=final_headers,
                            params=params,
                            json=json_data,
                            timeout=timeout,
                            verify=False
                        )
                else:
                    # 没有 UI User 或 get_token 失败，执行 API login 重试
                    token = self._ensure_token()
                    final_headers["x-auth-token"] = token
                    final_headers["x-access-token"] = token
                    response = self._session.request(
                        method=method,
                        url=url,
                        headers=final_headers,
                        params=params,
                        json=json_data,
                        timeout=timeout,
                        verify=False
                    )

                duration_ms = int((time.time() - start_time) * 1000)
                success = response.ok

                # 记录重试日志
                retry_reason = "worker_token" if worker_token else "api_login"
                logger.log_aw_call(
                    aw_name=self._aw_name,
                    method=f"{method}_retry_after_401_{retry_reason}",
                    args=log_args,
                    success=success,
                    result={"status_code": response.status_code, "body": response.text[:500]},
                    duration_ms=duration_ms
                )

                if not success:
                    raise ApiError(method, response.status_code, response.text[:200])

                return response

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

    def _get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        need_token: bool = True
    ) -> Dict[str, Any]:
        """GET 请求。

        Args:
            url: 请求 URL。
            params: URL 参数。
            headers: 额外的请求头（可选）。
            need_token: 是否需要 token，默认 True（登录接口除外）。

        Returns:
            响应 JSON 数据。
        """
        # 添加时间戳参数
        if params is None:
            params = {}
        params["ts"] = int(time.time())

        response = self._request_with_log("GET", url, params=params, headers=headers, need_token=need_token)
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

    def _put(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        need_token: bool = True
    ) -> None:
        """PUT 请求。

        Args:
            url: 请求 URL。
            data: JSON 请求体。
            headers: 额外的请求头（可选）。
            params: 额外的查询参数（可选）。
            need_token: 是否需要登录 token，默认 True。

        Raises:
            ApiError: 请求失败时抛出。
        """
        # 合并时间戳和额外参数
        final_params = {"ts": int(time.time())}
        if params:
            final_params.update(params)

        self._request_with_log(
            "PUT", url,
            params=final_params,
            json_data=data,
            headers=headers,
            need_token=need_token
        )