"""UserManager 单元测试。"""

import pytest
from unittest.mock import Mock, patch

from common.user_manager import UserManager, UserManagerError


class TestApplyRemoteRetry:
    """测试 _apply_remote 重试机制。"""

    def test_apply_success_no_retry(self):
        """正常申请成功，不触发重试。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 900,
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "userA": {
                    "ip": "192.168.0.1",
                    "port": 8080,
                    "account": "test",
                    "password": "pass",
                    "device_type": "web",
                    "id": "machine-1"
                }
            }
        }
        mock_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=mock_response):
            result = manager._apply_remote({"userA": "web"})
            assert "userA" in result
            assert result["userA"].ip == "192.168.0.1"

    def test_apply_env_not_enough_retry_success(self):
        """机器不足触发重试，最终成功。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 45,  # 测试用短时间
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        # 第一次返回 env not enough，第二次返回成功
        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "env not enough"}
        fail_response.raise_for_status = Mock()

        success_response = Mock()
        success_response.json.return_value = {
            "status": "success",
            "data": {
                "userA": {
                    "ip": "192.168.0.1",
                    "port": 8080,
                    "account": "test",
                    "password": "pass",
                    "device_type": "web",
                    "id": "machine-1"
                }
            }
        }
        success_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', side_effect=[fail_response, success_response]):
            with patch('time.sleep') as mock_sleep:
                result = manager._apply_remote({"userA": "web"})
                assert "userA" in result
                mock_sleep.assert_called_once_with(15)

    def test_apply_env_not_enough_retry_timeout(self):
        """机器不足重试超时，最终失败。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 45,
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        # 每次都返回 env not enough（最多重试 3 次）
        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "env not enough"}
        fail_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=fail_response):
            with patch('time.sleep') as mock_sleep:
                with pytest.raises(UserManagerError) as exc_info:
                    manager._apply_remote({"userA": "web"})
                assert "机器资源不足" in str(exc_info.value)
                assert mock_sleep.call_count == 3  # 45/15=3 次重试

    def test_apply_other_error_no_retry(self):
        """其他错误直接失败，不重试。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 900,
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "account locked"}
        fail_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=fail_response):
            with patch('time.sleep') as mock_sleep:
                with pytest.raises(UserManagerError) as exc_info:
                    manager._apply_remote({"userA": "web"})
                assert "account locked" in str(exc_info.value)
                mock_sleep.assert_not_called()

    def test_apply_default_config(self):
        """配置缺失时使用默认值。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30
            }
        })

        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "env not enough"}
        fail_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=fail_response):
            with patch('time.sleep') as mock_sleep:
                with pytest.raises(UserManagerError):
                    manager._apply_remote({"userA": "web"})
                # 默认值: 900/15 = 60 次重试
                assert mock_sleep.call_count == 60