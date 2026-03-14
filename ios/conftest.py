"""
iOS 端 pytest fixtures。
"""

import pytest

from common.testagent_client import TestagentClient


@pytest.fixture(scope="session")
def ios_client() -> TestagentClient:
    """iOS 端 testagent 客户端。

    Returns:
        TestagentClient 实例，平台固定为 ios。
    """
    client = TestagentClient()
    yield client


@pytest.fixture(scope="session")
def ios_config() -> dict:
    """iOS 端测试配置。

    Returns:
        配置字典。
    """
    return {
        "platform": "ios",
        "bundle_id": "com.example.app",
        "timeout": 30,
        "screenshot_on_failure": True,
    }