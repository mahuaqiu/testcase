"""用户资源管理器。

负责调用外部 API 申请和释放用户机器资源。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests

from common.config_loader import ConfigLoader


@dataclass
class UserResource:
    """用户资源数据类。

    存储单个用户的所有资源信息。

    Attributes:
        user_id: 用户标识，如 userA、userB。
        platform: 平台类型，如 web、windows、mac、ios、android。
        ip: 机器 IP 地址。
        account: 登录账号。
        password: 登录密码。
        user_type: 用户类型，如 normal、admin。
        extra: 扩展信息字典。
    """

    user_id: str
    platform: str
    ip: str
    account: str
    password: str
    user_type: str = "normal"
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

        rm_config = self.config.get("resource_manager", {})
        self._base_url = rm_config.get("base_url", "").rstrip("/")
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
        return self._apply_remote(users)

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
                account=mock_data.get("account", ""),
                password=mock_data.get("password", ""),
                user_type=mock_data.get("type", "normal"),
                extra=mock_data.get("extra", {}),
            )

        return self._resources

    def _apply_remote(self, users: Dict[str, str]) -> Dict[str, UserResource]:
        """远程模式：调用 API 申请资源。

        Args:
            users: 用户需求字典。

        Returns:
            用户资源字典。

        Raises:
            UserManagerError: API 调用失败时抛出。
        """
        url = f"{self._base_url}/env/create"
        try:
            response = self._session.post(url, json=users, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as e:
            raise UserManagerError(f"申请用户资源超时: {e}") from e
        except requests.RequestException as e:
            raise UserManagerError(f"申请用户资源失败: {e}") from e

        # 解析响应
        for user_id, user_data in data.items():
            self._resources[user_id] = UserResource(
                user_id=user_id,
                platform=user_data.get("platform", users.get(user_id, "")),
                ip=user_data.get("ip", ""),
                account=user_data.get("account", ""),
                password=user_data.get("password", ""),
                user_type=user_data.get("type", "normal"),
                extra=user_data.get("extra", {}),
            )

        return self._resources

    def release(self) -> None:
        """释放所有已申请的用户资源。

        调用外部 API 释放资源。释放失败不会抛出异常，但会记录日志。
        """
        if not self._resources or not self._base_url:
            return

        users = {uid: res.platform for uid, res in self._resources.items()}
        url = f"{self._base_url}/env/release"

        try:
            self._session.post(url, json=users, timeout=self._timeout)
        except requests.RequestException:
            # 释放失败不阻塞测试流程
            pass
        finally:
            self._resources.clear()

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