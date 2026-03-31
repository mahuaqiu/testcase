"""用户资源管理器。

负责调用外部 API 申请和释放用户机器资源。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import logging
import time

import requests

from common.config_loader import ConfigLoader
from common.keepalive import KeepAliveManager

logger = logging.getLogger(__name__)


@dataclass
class UserResource:
    """用户资源数据类。

    存储单个用户的所有资源信息。

    Attributes:
        user_id: 用户标识，如 userA、userB。
        platform: 平台类型，如 web、windows、mac、ios、android。
        ip: 机器 IP 地址。
        port: Worker 端口。
        account: 登录账号。
        password: 登录密码。
        name: 与会者姓名。
        user_type: 用户类型，如 normal、admin。
        machine_id: 执行机机器 ID（用于保活和释放）。
        extra: 扩展信息字典。
    """

    user_id: str
    platform: str
    ip: str
    port: int
    account: str
    password: str
    name: str = ""
    user_type: str = "normal"
    machine_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class UserManagerError(Exception):
    """用户资源管理异常。

    当资源申请、释放或查询失败时抛出。
    """

    pass


class UserManager:
    """用户资源管理器。

    负责调用外部 API 申请和释放用户机器资源。
    支持上下文管理器，确保资源自动释放。

    Usage:
        with UserManager(config) as manager:
            resources = manager.apply({"userA": "web", "userB": "windows"})
            user_a = manager.get_user("userA")
            print(user_a.account, user_a.password)
        # 退出时自动释放资源
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化用户资源管理器。

        Args:
            config: 配置字典，如果为 None 则自动加载。
        """
        self.config = config or ConfigLoader().load()
        self._resources: Dict[str, UserResource] = {}
        self._session = requests.Session()
        self._raw_resources: Dict[str, Any] = {}  # 存储原始响应
        self._keepalive: Optional[KeepAliveManager] = None

        rm_config = self.config.get("resource_manager", {})
        self._base_url = rm_config.get("base_url", "").rstrip("/")
        self._namespace = rm_config.get("namespace", "default")
        self._timeout = rm_config.get("timeout", 30)
        self._mock_users = rm_config.get("mock_users", {})

    def apply(self, users: Dict[str, str]) -> Dict[str, UserResource]:
        """申请用户资源。

        当 base_url 为空时，使用 mock_users 本地调试模式。
        当 base_url 配置时，调用外部 API 申请用户机器资源。

        Args:
            users: 用户需求字典，key 为用户标识（如 userA），
                   value 为平台类型（如 web）。

        Returns:
            用户资源字典，key 为用户标识，value 为 UserResource 实例。

        Raises:
            UserManagerError: 申请失败时抛出。

        Example:
            manager.apply({"userA": "web", "userB": "windows"})
        """
        if not users:
            return {}

        # 本地调试模式：使用 mock_users
        if not self._base_url:
            return self._apply_mock(users)

        # 远程模式：调用 API
        result = self._apply_remote(users)

        # 启动保活
        if self._base_url and self._raw_resources:
            self._keepalive = KeepAliveManager(self._base_url, self._timeout)
            self._keepalive.start(self._raw_resources)

        return result

    def _apply_mock(self, users: Dict[str, str]) -> Dict[str, UserResource]:
        """本地调试模式：使用 mock_users 配置。

        Args:
            users: 用户需求字典。

        Returns:
            用户资源字典。

        Raises:
            UserManagerError: mock_users 中未配置对应用户时抛出。
        """
        for user_id, platform in users.items():
            if user_id not in self._mock_users:
                raise UserManagerError(
                    f"本地调试模式：mock_users 中未配置用户 '{user_id}'，"
                    f"请在 config.yaml 的 resource_manager.mock_users 中添加"
                )

            mock_data = self._mock_users[user_id]
            self._resources[user_id] = UserResource(
                user_id=user_id,
                platform=platform,
                ip=mock_data.get("ip", "127.0.0.1"),
                port=mock_data.get("port", 8080),
                account=mock_data.get("account", ""),
                password=mock_data.get("password", ""),
                name=mock_data.get("name", ""),
                user_type=mock_data.get("type", "normal"),
                extra=mock_data.get("extra", {}),
            )

        return self._resources

    def _apply_remote(self, users: Dict[str, str]) -> Dict[str, UserResource]:
        """远程模式：调用 API 申请资源，支持重试。

        Args:
            users: 用户需求字典。

        Returns:
            用户资源字典。

        Raises:
            UserManagerError: API 调用失败时抛出。
        """
        # 加载重试配置
        retry_config = self.config.get("resource_manager", {}).get("retry", {})
        max_wait_seconds = retry_config.get("max_wait_seconds", 900)
        retry_interval = retry_config.get("retry_interval", 15)
        retryable_errors = retry_config.get("retryable_errors", ["env not enough"])

        max_retries = max_wait_seconds // retry_interval

        url = f"{self._base_url}/env/{self._namespace}/application"

        for attempt in range(max_retries + 1):
            # 发起申请请求
            try:
                response = self._session.post(url, json=users, timeout=self._timeout)
                response.raise_for_status()
                data = response.json()
            except requests.Timeout as e:
                raise UserManagerError(f"申请用户资源超时: {e}") from e
            except requests.RequestException as e:
                raise UserManagerError(f"申请用户资源失败: {e}") from e

            # 检查响应状态
            if data.get("status") == "success":
                return self._parse_response(data, users)

            error_msg = data.get("result", "未知错误")

            # 判断是否可重试
            if error_msg in retryable_errors:
                if attempt < max_retries:
                    logger.info(
                        f"机器资源不足，等待 {retry_interval} 秒后重试（第 {attempt+1}/{max_retries} 次）"
                    )
                    time.sleep(retry_interval)
                    continue
                else:
                    raise UserManagerError(
                        f"申请用户资源失败：机器资源不足，已等待 {max_wait_seconds} 秒"
                    )
            else:
                # 其他错误直接失败
                raise UserManagerError(f"申请用户资源失败: {error_msg}")

    def _parse_response(self, data: dict, users: Dict[str, str]) -> Dict[str, UserResource]:
        """解析成功响应，提取用户资源。

        Args:
            data: API 成功响应数据。
            users: 用户需求字典。

        Returns:
            用户资源字典。
        """
        resources_data = data.get("data", {})
        # 保存原始响应中的机器 ID（用于 keepalive 和 release）
        self._raw_resources = {
            user_id: user_data for user_id, user_data in resources_data.items()
        }

        # 解析响应
        # 已知字段列表，其余字段收集到 extra
        known_fields = {
            "id", "ip", "port", "device_type", "device_sn",
            "account", "password", "name", "type", "extra"
        }
        for user_id, user_data in resources_data.items():
            # 收集未知字段到 extra（如 email、department 等）
            extra = {k: v for k, v in user_data.items() if k not in known_fields}
            self._resources[user_id] = UserResource(
                user_id=user_id,
                platform=user_data.get("device_type", users.get(user_id, "")),
                ip=user_data.get("ip", ""),
                port=user_data.get("port", 8080),
                account=user_data.get("account", ""),
                password=user_data.get("password", ""),
                name=user_data.get("name", ""),
                user_type=user_data.get("type", "normal"),
                machine_id=user_data.get("id"),
                extra=extra,
            )

        return self._resources

    def release(self) -> None:
        """释放所有已申请的用户资源。

        调用外部 API 释放资源。释放失败不会抛出异常，但会记录日志。
        """
        # 先停止保活
        if self._keepalive:
            self._keepalive.stop()
            self._keepalive = None

        if not self._raw_resources or not self._base_url:
            return

        # 构建 EnvMachineIdItem 列表
        machine_ids = [{"id": user_data.get("id")} for user_data in self._raw_resources.values() if user_data.get("id")]
        if not machine_ids:
            return

        url = f"{self._base_url}/env/release"

        try:
            self._session.post(url, json=machine_ids, timeout=self._timeout)
        except requests.RequestException:
            # 释放失败不阻塞测试流程
            pass
        finally:
            self._resources.clear()
            self._raw_resources.clear()

    def get_user(self, user_id: str) -> UserResource:
        """获取指定用户的资源信息。

        Args:
            user_id: 用户标识，如 userA、userB。

        Returns:
            UserResource 实例。

        Raises:
            UserManagerError: 用户资源不存在时抛出。
        """
        if user_id not in self._resources:
            raise UserManagerError(f"用户资源不存在: {user_id}")
        return self._resources[user_id]

    def get_account(self, user_id: str) -> str:
        """获取指定用户的账号。

        Args:
            user_id: 用户标识。

        Returns:
            账号字符串。
        """
        return self.get_user(user_id).account

    def get_password(self, user_id: str) -> str:
        """获取指定用户的密码。

        Args:
            user_id: 用户标识。

        Returns:
            密码字符串。
        """
        return self.get_user(user_id).password

    def get_platform(self, user_id: str) -> str:
        """获取指定用户的平台类型。

        Args:
            user_id: 用户标识。

        Returns:
            平台类型字符串。
        """
        return self.get_user(user_id).platform

    def get_ip(self, user_id: str) -> str:
        """获取指定用户的机器 IP。

        Args:
            user_id: 用户标识。

        Returns:
            IP 地址字符串。
        """
        return self.get_user(user_id).ip

    def has_user(self, user_id: str) -> bool:
        """检查用户资源是否存在。

        Args:
            user_id: 用户标识。

        Returns:
            存在返回 True，否则返回 False。
        """
        return user_id in self._resources

    def get_raw_resources(self) -> Dict[str, Any]:
        """获取原始资源响应（用于 keepalive 和 release）。

        Returns:
            原始响应字典。
        """
        return self._raw_resources.copy()

    @property
    def resources(self) -> Dict[str, UserResource]:
        """获取所有已申请的用户资源。

        Returns:
            用户资源字典。
        """
        return self._resources.copy()

    def __enter__(self) -> "UserManager":
        """进入上下文管理器。"""
        return self

    def __exit__(self, *args) -> None:
        """退出上下文管理器，自动释放资源。"""
        self.release()