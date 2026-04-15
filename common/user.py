"""User 用户资源类。"""

from typing import Any, Dict, Optional

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
        name: 与会者姓名。
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
        name: str = "",
        _ui_user_id: Optional[str] = None,  # 新增：API User 关联的 UI User ID
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
            name: 与会者姓名。
            _ui_user_id: API User 关联的 UI User ID。
            **extra: 扩展信息。
        """
        self.user_id = user_id
        self.platform = platform
        self.ip = ip
        self.port = port
        self.account = account
        self.password = password
        self.name = name
        self.extra = extra
        self._ui_user_id = _ui_user_id  # 独立属性，不存入 extra
        self._user_instances_ref: Optional[Dict[str, "User"]] = None  # 新增：user_instances 引用
        self._used = False  # 新增：用户是否被实际使用

        # API 平台不需要 TestagentClient
        if platform == "api":
            self.client = None
        else:
            # 初始化 TestagentClient，从配置读取超时设置
            base_url = f"http://{ip}:{port}"
            config = ConfigLoader().load()
            testagent_config = config.get("testagent", {})
            connect_timeout = testagent_config.get("connect_timeout", 30)
            read_timeout = testagent_config.get("read_timeout", 60)
            self.client = TestagentClient(base_url, connect_timeout, read_timeout)

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
        """代理转发 AW 方法调用和 extra 字段访问。

        查找优先级：
        1. AW 方法
        2. extra 字段（支持动态扩展）

        Args:
            name: 方法名或属性名。

        Returns:
            AW 方法或 extra 字段值。

        Raises:
            AttributeError: 方法或属性不存在。
        """
        # 1. 查找 AW 方法
        for aw_instance in self._aw_instances.values():
            if hasattr(aw_instance, name):
                attr = getattr(aw_instance, name)
                # 如果是可调用方法，标记用户已使用
                if callable(attr):
                    self._used = True
                return attr

        # 2. 查找 extra 字段（支持动态扩展）
        # 使用 object.__getattribute__ 安全访问 extra
        try:
            extra = object.__getattribute__(self, "extra")
            if name in extra:
                return extra[name]
        except AttributeError:
            pass

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

    def _get_ui_user(self) -> Optional["User"]:
        """获取关联的 UI User 实例。

        Returns:
            UI User 实例，如果没有关联则返回 None。
        """
        if not self._ui_user_id:
            return None
        if not self._user_instances_ref:
            return None
        return self._user_instances_ref.get(self._ui_user_id)

    def _get_ui_client(self) -> Optional["TestagentClient"]:
        """获取关联 UI User 的 TestagentClient。

        Returns:
            UI User 的 TestagentClient，如果没有关联则返回 None。
        """
        ui_user = self._get_ui_user()
        return ui_user.client if ui_user else None

    def _get_ui_platform(self) -> Optional[str]:
        """获取关联 UI User 的平台类型。

        Returns:
            UI User 的平台类型，如果没有关联则返回 None。
        """
        ui_user = self._get_ui_user()
        return ui_user.platform if ui_user else None