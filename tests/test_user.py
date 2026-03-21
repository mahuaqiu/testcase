"""User 类测试。"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from common.user import User


class TestUser:
    """User 类测试类。"""

    def test_user_initialization(self):
        """测试用户初始化。"""
        with patch("common.user.TestagentClient") as mock_client:
            user = User(
                user_id="userA",
                platform="web",
                ip="192.168.1.100",
                port=8080,
                account="test001",
                password="Password@123"
            )

            assert user.user_id == "userA"
            assert user.platform == "web"
            assert user.ip == "192.168.1.100"
            assert user.port == 8080
            assert user.account == "test001"
            assert user.password == "Password@123"

    def test_user_loads_common_aw(self):
        """测试加载公共 AW。"""
        with patch("common.user.TestagentClient"):
            user = User(
                user_id="userA",
                platform="web",
                ip="127.0.0.1",
                port=8080,
                account="test",
                password="test"
            )

            # 验证加载了公共 AW 实例
            assert len(user._aw_instances) > 0

    def test_user_proxy_method_call(self):
        """测试代理方法调用。"""
        with patch("common.user.TestagentClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            user = User(
                user_id="userA",
                platform="web",
                ip="127.0.0.1",
                port=8080,
                account="test",
                password="test"
            )

            # Mock AW 方法
            user._aw_instances["MockAW"] = MagicMock()
            user._aw_instances["MockAW"].do_test = MagicMock(return_value="success")

            result = user.do_test()
            assert result == "success"

    def test_user_raises_attribute_error_for_unknown_method(self):
        """测试未知方法抛出 AttributeError。"""
        with patch("common.user.TestagentClient"):
            user = User(
                user_id="userA",
                platform="web",
                ip="127.0.0.1",
                port=8080,
                account="test",
                password="test"
            )

            with pytest.raises(AttributeError):
                user.unknown_method()