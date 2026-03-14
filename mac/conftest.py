"""
Mac 端 pytest fixtures。
"""

import pytest

from common.testagent_client import TestagentClient


@pytest.fixture(scope="session")
def mac_client() -> TestagentClient:
    """Mac 端 testagent 客户端。

    Returns:
        TestagentClient 实例，平台固定为 mac。
    """
    client = TestagentClient()
    yield client


@pytest.fixture(scope="session")
def mac_config() -> dict:
    """Mac 端测试配置。

    Returns:
        配置字典。
    """
    return {
        "platform": "mac",
        "timeout": 30,
        "screenshot_on_failure": True,
    }