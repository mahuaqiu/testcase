"""
全局 pytest 配置。

提供用户资源管理、hooks 执行、失败截图、报告生成等功能。
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import pytest

from common.config_loader import ConfigLoader
from common.user_manager import UserManager
from common.user import User
from common.hooks_resolver import HooksResolver
from common.keepalive import KeepAliveManager
from common.report_logger import ReportLogger
from common.report_generator import HTMLReportGenerator


# ── 全局配置 ─────────────────────────────────────────

_config = None
_keepalive_managers: Dict[str, KeepAliveManager] = {}


def get_config() -> Dict[str, Any]:
    """获取全局配置（单例）。"""
    global _config
    if _config is None:
        _config = ConfigLoader().load()
    return _config


# ── 标记注册 ─────────────────────────────────────────

def pytest_configure(config):
    """注册自定义标记。"""
    config.addinivalue_line(
        "markers", "users: 用户资源需求标记，如 @pytest.mark.users({'userA': 'web'})"
    )
    config.addinivalue_line(
        "markers", "hooks: 用例级别 hooks 标记，如 @pytest.mark.hooks(setup=['+login'])"
    )


# ── 用户资源 Fixture ─────────────────────────────────

@pytest.fixture(scope="function")
def users(request) -> Dict[str, User]:
    """用户资源 fixture。

    自动申请用户资源、执行 hooks、启动保活、生成报告。

    Returns:
        用户资源字典，key 为 userA/userB，value 为 User 实例。
    """
    marker = request.node.get_closest_marker("users")
    if not marker:
        return {}

    users_requirement = marker.args[0] if marker.args else marker.kwargs
    if not users_requirement:
        return {}

    # 重置日志收集器
    ReportLogger.reset()
    logger = ReportLogger.get_current()

    config = get_config()
    raw_resources: Dict[str, Any] = {}
    user_instances: Dict[str, User] = {}

    with UserManager(config) as manager:
        resources = manager.apply(users_requirement)
        raw_resources = manager.get_raw_resources()

        # 创建 User 实例
        for user_id, resource in resources.items():
            user = User(
                user_id=user_id,
                platform=resource.platform,
                ip=resource.ip,
                port=resource.port,
                account=resource.account,
                password=resource.password,
                **resource.extra
            )
            user_instances[user_id] = user

        # 启动保活（远程模式）
        rm_config = config.get("resource_manager", {})
        base_url = rm_config.get("base_url", "")
        if base_url:
            for user_id, user in user_instances.items():
                keepalive = KeepAliveManager(base_url, rm_config.get("timeout", 30))
                keepalive.start({user_id: raw_resources.get(user_id, {})})
                _keepalive_managers[user_id] = keepalive

        # 执行 setup hooks
        hooks_config = config.get("hooks", {})
        case_hooks = _get_case_hooks(request.node)

        for user_id, user in user_instances.items():
            final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks)
            _execute_hooks(user, final_hooks.get("setup", []))

        yield user_instances

        # 执行 teardown hooks
        for user_id, user in user_instances.items():
            final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks)
            _execute_hooks(user, final_hooks.get("teardown", []))

        # 停止保活
        for user_id, keepalive in _keepalive_managers.items():
            keepalive.stop()
        _keepalive_managers.clear()

        logger.log_step("用例结束")


# ── 报告生成 Hook ─────────────────────────────────

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """测试结束后生成报告。"""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        logger = ReportLogger.get_current()

        # 失败时截图
        if report.failed and "users" in item.funcargs:
            users = item.funcargs["users"]
            for user_id, user in users.items():
                try:
                    base64_data = user.screenshot()
                    if base64_data:
                        logger.log_screenshot(user_id, base64_data)
                except Exception:
                    pass

            # 记录错误
            logger.log_error(str(report.longrepr))

        # 生成报告（始终在项目根目录下）
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        project_root = Path(__file__).parent  # conftest.py 所在目录即项目根目录
        report_dir = project_root / "report" / timestamp
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{item.name}.html"

        HTMLReportGenerator.generate(
            report_path=report_path,
            case_name=item.name,
            case_title=item.instance.__doc__ or "" if item.instance else "",
            logs=logger.get_logs(),
            duration_ms=logger.get_duration(),
            status="passed" if report.passed else "failed",
            error_msg=str(report.longrepr) if report.failed else ""
        )


# ── 辅助函数 ─────────────────────────────────────────

def _get_case_hooks(node) -> Dict[str, Any]:
    """获取用例级别的 hooks 标记。"""
    marker = node.get_closest_marker("hooks")
    if not marker:
        return {}
    return marker.args[0] if marker.args else marker.kwargs


def _execute_hooks(user: User, hooks: list) -> None:
    """执行 hooks 方法。

    支持两种格式：
    - 字符串: "start_app" - 使用默认参数
    - 字典: {"start_app": "edge"} - 传入参数
    """
    logger = ReportLogger.get_current()
    for hook_item in hooks:
        # 解析 hook 名称和参数
        if isinstance(hook_item, dict):
            hook_name, hook_arg = next(iter(hook_item.items()))
        else:
            hook_name = hook_item
            hook_arg = None

        method_name = f"do_{hook_name}"
        if hasattr(user, method_name):
            try:
                logger.log_step(f"执行 hook: {hook_name}" + (f"({hook_arg})" if hook_arg else ""))
                method = getattr(user, method_name)
                if hook_arg is not None:
                    method(hook_arg)
                else:
                    method()
            except Exception as e:
                logger.log_error(f"Hook 执行失败 [{hook_name}]: {e}")