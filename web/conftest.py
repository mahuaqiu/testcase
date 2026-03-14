"""
Web 端 pytest fixtures。
"""

import pytest

from common.testagent_client import TestagentClient


@pytest.fixture(scope="session")
def web_client() -> TestagentClient:
    """Web 端 testagent 客户端。

    Returns:
        TestagentClient 实例，平台固定为 web。
    """
    client = TestagentClient()
    yield client


@pytest.fixture(scope="session")
def web_config() -> dict:
    """Web 端测试配置。

    Returns:
        配置字典。
    """
    return {
        "platform": "web",
        "base_url": "http://localhost:3000",
        "timeout": 30,
        "screenshot_on_failure": True,
    }