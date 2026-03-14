"""
全局 pytest 配置。

提供所有端共用的 fixtures 和 hooks。
"""

from typing import Dict

import pytest

from common.data_factory import DataFactory
from common.user_manager import UserManager, UserManagerError, UserResource


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
    config.addinivalue_line(
        "markers", "users: 用户资源需求标记，如 @pytest.mark.users({'userA': 'web'})"
    )


@pytest.fixture(scope="function")
def users(request) -> Dict[str, UserResource]:
    """用户资源 fixture。

    自动申请和释放用户资源，用例级别生命周期。

    用法:
        在测试类上声明: @pytest.mark.users({"userA": "web"})

    Returns:
        用户资源字典，key 为 userA/userB，value 为 UserResource 实例。

    Raises:
        UserManagerError: 资源申请失败时抛出。
    """
    # 获取 users 标记
    marker = request.node.get_closest_marker("users")
    if not marker:
        return {}

    users_requirement = marker.args[0] if marker.args else marker.kwargs

    # 加载配置并申请资源
    from common.config_loader import ConfigLoader

    config = ConfigLoader().load()

    with UserManager(config) as manager:
        resources = manager.apply(users_requirement)
        yield resources
        # 退出 context manager 时自动释放