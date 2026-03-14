"""
Android 端 pytest fixtures。
"""

import pytest

from common.testagent_client import TestagentClient


@pytest.fixture(scope="session")
def android_client() -> TestagentClient:
    """Android 端 testagent 客户端。

    Returns:
        TestagentClient 实例，平台固定为 android。
    """
    client = TestagentClient()
    yield client


@pytest.fixture(scope="session")
def android_config() -> dict:
    """Android 端测试配置。

    Returns:
        配置字典。
    """
    return {
        "platform": "android",
        "package_name": "com.example.app",
        "timeout": 30,
        "screenshot_on_failure": True,
    }