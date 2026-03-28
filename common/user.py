"""User 用户资源类。"""

from typing import Any, Dict

from common.config_loader import ConfigLoader
from common.testagent_client import TestagentClient


class User:
    """用户资源类，代理转发 AW 方法。

    自动加载公共 AW 和对应平台的 AW 实例，
    通过 __getattr__ 实现方法调用的代理转发。

    Attributes:
        user_id: 用户标识，如 userA、userB。
        platform: 平台类型，如 web、windows。
        ip: Worker IP 地址。
        port: Worker 端口。
        account: 登录账号。
        password: 登录密码。
        extra: 扩展信息。
    """

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
            # 初始化 TestagentClient，从配置读取超时设置
            base_url = f"http://{ip}:{port}"
            config = ConfigLoader().load()
            timeout = config.get("testagent", {}).get("timeout", 60)
            self.client = TestagentClient(base_url, timeout)

        # 加载 AW 实例
        self._aw_instances: Dict[str, Any] = {}
        self._load_aw_modules()

    def _load_aw_modules(self) -> None:
        """加载公共 AW 和对应平台的 AW。"""
        from aw import get_platform_aw_classes

        # 1. 加载公共 AW
        for aw_class in get_platform_aw_classes("common"):
            instance = aw_class(self.client, self)
            self._aw_instances[aw_class.__name__] = instance

        # 2. 加载平台 AW（包括 api）
        if self.platform == "api":
            # API 平台加载 api 目录下的 AW，client 传 None
            for aw_class in get_platform_aw_classes("api"):
                instance = aw_class(None, self)
                self._aw_instances[aw_class.__name__] = instance
        else:
            # 其他平台加载对应平台的 AW
            for aw_class in get_platform_aw_classes(self.platform):
                instance = aw_class(self.client, self)
                self._aw_instances[aw_class.__name__] = instance

    def __getattr__(self, name: str) -> Any:
        """代理转发 AW 方法调用。

        Args:
            name: 方法名。

        Returns:
            AW 方法。

        Raises:
            AttributeError: 方法不存在。
        """
        for aw_instance in self._aw_instances.values():
            if hasattr(aw_instance, name):
                return getattr(aw_instance, name)

        raise AttributeError(
            f"'{type(self).__name__}' 对象没有属性 '{name}'"
        )

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
            action = result["actions"][0]
            # 优先取 screenshot 字段，其次取 output 字段
            return action.get("screenshot") or action.get("output", "")
        return ""