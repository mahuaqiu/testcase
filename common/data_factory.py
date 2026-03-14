"""
测试数据工厂。

提供测试用例的测试数据生成功能。
"""

import random
import string
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


class DataFactory:
    """测试数据工厂。

    提供各种类型的测试数据生成方法。

    Example:
        user = DataFactory.random_user()
        email = DataFactory.random_email()
        phone = DataFactory.random_phone()
    """

    # 预设测试账号
    TEST_USERS = {
        "admin": {"username": "admin", "password": "Admin@123", "role": "admin"},
        "user": {"username": "testuser", "password": "Test@123", "role": "user"},
    }

    @classmethod
    def random_string(cls, length: int = 10) -> str:
        """生成随机字符串。

        Args:
            length: 字符串长度。

        Returns:
            随机字符串。
        """
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    @classmethod
    def random_email(cls, domain: str = "test.com") -> str:
        """生成随机邮箱。

        Args:
            domain: 邮箱域名。

        Returns:
            随机邮箱地址。
        """
        prefix = cls.random_string(8).lower()
        return f"{prefix}@{domain}"

    @classmethod
    def random_phone(cls) -> str:
        """生成随机手机号（中国格式）。

        Returns:
            随机手机号。
        """
        prefixes = ["138", "139", "150", "151", "152", "186", "187", "188"]
        prefix = random.choice(prefixes)
        suffix = "".join(random.choices(string.digits, k=8))
        return prefix + suffix

    @classmethod
    def random_int(cls, min_val: int = 1, max_val: int = 100) -> int:
        """生成随机整数。

        Args:
            min_val: 最小值。
            max_val: 最大值。

        Returns:
            随机整数。
        """
        return random.randint(min_val, max_val)

    @classmethod
    def random_float(
        cls,
        min_val: float = 0.0,
        max_val: float = 100.0,
        decimals: int = 2,
    ) -> float:
        """生成随机浮点数。

        Args:
            min_val: 最小值。
            max_val: 最大值。
            decimals: 小数位数。

        Returns:
            随机浮点数。
        """
        value = random.uniform(min_val, max_val)
        return round(value, decimals)

    @classmethod
    def random_uuid(cls) -> str:
        """生成 UUID。

        Returns:
            UUID 字符串。
        """
        return str(uuid.uuid4())

    @classmethod
    def random_date(
        cls,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        fmt: str = "%Y-%m-%d",
    ) -> str:
        """生成随机日期。

        Args:
            start: 开始日期，默认为今天。
            end: 结束日期，默认为一年后。
            fmt: 日期格式。

        Returns:
            格式化的日期字符串。
        """
        start = start or datetime.now()
        end = end or datetime.now() + timedelta(days=365)
        delta = end - start
        random_days = random.randint(0, delta.days)
        random_date = start + timedelta(days=random_days)
        return random_date.strftime(fmt)

    @classmethod
    def random_user(
        cls,
        username: Optional[str] = None,
        password: Optional[str] = None,
        role: str = "user",
    ) -> Dict[str, str]:
        """生成随机用户数据。

        Args:
            username: 用户名，不指定则自动生成。
            password: 密码，不指定则自动生成。
            role: 角色。

        Returns:
            用户数据字典。
        """
        return {
            "username": username or f"user_{cls.random_string(6)}",
            "password": password or f"Pass_{cls.random_string(8)}",
            "email": cls.random_email(),
            "phone": cls.random_phone(),
            "role": role,
        }

    @classmethod
    def get_test_user(cls, user_type: str = "user") -> Dict[str, str]:
        """获取预设测试账号。

        Args:
            user_type: 账号类型（admin/user）。

        Returns:
            预设账号数据。

        Raises:
            ValueError: 账号类型不存在时抛出。
        """
        if user_type not in cls.TEST_USERS:
            raise ValueError(f"未知的账号类型: {user_type}")
        return cls.TEST_USERS[user_type].copy()

    @classmethod
    def random_item(cls, items: List[Any]) -> Any:
        """从列表中随机选择一个元素。

        Args:
            items: 列表。

        Returns:
            随机选择的元素。
        """
        return random.choice(items)

    @classmethod
    def random_items(cls, items: List[Any], count: int) -> List[Any]:
        """从列表中随机选择多个元素（不重复）。

        Args:
            items: 列表。
            count: 选择数量。

        Returns:
            随机选择的元素列表。
        """
        count = min(count, len(items))
        return random.sample(items, count)