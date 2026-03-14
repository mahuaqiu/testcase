"""
Windows 端 pytest fixtures。
"""

import pytest

from common.testagent_client import TestagentClient


@pytest.fixture(scope="session")
def windows_client() -> TestagentClient:
    """Windows 端 testagent 客户端。

    Returns:
        TestagentClient 实例，平台固定为 windows。
    """
    client = TestagentClient()
    # 可在此处初始化 Windows 端测试环境
    yield client
    # 清理工作


@pytest.fixture(scope="session")
def windows_config() -> dict:
    """Windows 端测试配置。

    Returns:
        配置字典。
    """
    return {
        "platform": "windows",
        "timeout": 30,
        "screenshot_on_failure": True,
    }