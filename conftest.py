"""
全局 pytest 配置。

提供所有端共用的 fixtures 和 hooks。
"""

import pytest

from common.data_factory import DataFactory


@pytest.fixture(scope="session")
def config():
    """全局配置。

    Returns:
        配置字典。
    """
    return {
        "testagent_url": "http://localhost:8080",
        "timeout": 30,
        "retry_count": 3,
        "screenshot_dir": "screenshots",
    }


@pytest.fixture(scope="session")
def data_factory() -> DataFactory:
    """数据工厂 fixture。

    Returns:
        DataFactory 实例。
    """
    return DataFactory()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """测试失败时截图（需要各端 conftest 配合实现）。"""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        # 调用各端的失败处理 hook
        if hasattr(item, "funcargs"):
            for name, value in item.funcargs.items():
                if hasattr(value, "screenshot"):
                    try:
                        value.screenshot(f"failure_{item.name}")
                    except Exception:
                        pass


def pytest_configure(config):
    """注册自定义标记。"""
    config.addinivalue_line("markers", "windows: Windows 端测试")
    config.addinivalue_line("markers", "web: Web 端测试")
    config.addinivalue_line("markers", "mac: Mac 端测试")
    config.addinivalue_line("markers", "ios: iOS 端测试")
    config.addinivalue_line("markers", "android: Android 端测试")
    config.addinivalue_line("markers", "smoke: 冒烟测试")
    config.addinivalue_line("markers", "regression: 回归测试")