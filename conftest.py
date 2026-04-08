"""
全局 pytest 配置。

提供用户资源管理、hooks 执行、失败截图、报告生成等功能。
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import pytest
import json

from common.config_loader import ConfigLoader
from common.user_manager import UserManager
from common.user import User
from common.hooks_resolver import HooksResolver
from common.keepalive import KeepAliveManager
from common.report_logger import ReportLogger
from common.report_generator import HTMLReportGenerator


# ── Hook 异障类 ─────────────────────────────────────────

class HookFailureError(Exception):
    """Hook 执行失障异常。

    用于区分 hook 失障和普通测试失障，便于 fixture 中正确处理流程。
    """
    def __init__(self, hook_name: str, original_error: Exception, hook_type: str):
        self.hook_name = hook_name
        self.original_error = original_error
        self.hook_type = hook_type  # "setup" 或 "teardown"
        super().__init__(f"Hook [{hook_type}/{hook_name}] 执行失障: {original_error}")


# ── 全局配置 ─────────────────────────────────────────

_config = None
_keepalive_managers: Dict[str, KeepAliveManager] = {}
_test_results: Dict[str, Dict[str, Any]] = {}  # 存储测试结果
_exe_param: Dict[str, Any] = {}  # 存储 exeParam 参数解析结果


def get_config() -> Dict[str, Any]:
    """获取全局配置（单例）。"""
    global _config
    if _config is None:
        _config = ConfigLoader().load()
    return _config


def get_exe_param() -> Dict[str, Any]:
    """获取 exeParam 参数（解析后的 JSON 字典）。"""
    return _exe_param


# ── 命令行参数注册 ─────────────────────────────────────────

def pytest_addoption(parser):
    """注册自定义命令行参数。"""
    parser.addoption(
        "--exeParam",
        action="store",
        default="{}",
        help="执行参数，JSON 字符串格式，如 --exeParam='{\"key\": \"value\"}'"
    )


# ── 标记注册 ─────────────────────────────────────────

def pytest_configure(config):
    """注册自定义标记，解析命令行参数。"""
    global _exe_param

    # 注册自定义标记
    config.addinivalue_line(
        "markers", "users: 用户资源需求标记，如 @pytest.mark.users({'userA': 'web'})"
    )
    config.addinivalue_line(
        "markers", "hooks: 用例级别 hooks 标记，如 @pytest.mark.hooks(setup=['+login'])"
    )
    config.addinivalue_line(
        "markers", "namespace: namespace 标记，如 @pytest.mark.namespace('web_public')"
    )

    # 解析 exeParam 参数
    exe_param_str = config.getoption("--exeParam", default="{}")
    try:
        _exe_param = json.loads(exe_param_str) if exe_param_str else {}
    except json.JSONDecodeError as e:
        print(f"[警告] exeParam 参数解析失败，将使用空字典: {e}")
        _exe_param = {}


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

    # 获取 namespace（优先级：用例标记 > 目录 conftest > 全局配置）
    namespace = _get_namespace(request.node, config)

    # 获取当前测试方法名作为 testcase_id
    testcase_id = request.node.name

    with UserManager(config, namespace=namespace) as manager:
        resources = manager.apply(users_requirement, testcase_id=testcase_id)
        raw_resources = manager.get_raw_resources()

        # 记录申请到的机器资源信息
        logger.log_step("申请用户资源", json.dumps(raw_resources, indent=2, ensure_ascii=False))

        # 创建 User 实例
        for user_id, resource in resources.items():
            user = User(
                user_id=user_id,
                platform=resource.platform,
                ip=resource.ip,
                port=resource.port,
                account=resource.account,
                password=resource.password,
                name=resource.name,
                **resource.extra
            )
            user_instances[user_id] = user

            # 支持 _api 后缀：创建同一账号的 API 实例
            api_user_id = f"{user_id}_api"
            api_user = User(
                user_id=api_user_id,
                platform="api",
                ip=resource.ip,
                port=resource.port,
                account=resource.account,
                password=resource.password,
                name=resource.name,
                _ui_user_id=user_id,  # 关联 UI User
                **resource.extra
            )
            user_instances[api_user_id] = api_user

        # 设置 API User 的 user_instances 引用
        for user_id, user in user_instances.items():
            if user_id.endswith("_api"):
                user._user_instances_ref = user_instances

        # 启动保活（远程模式）
        rm_config = config.get("resource_manager", {})
        base_url = rm_config.get("base_url", "")
        if base_url:
            for user_id, user in user_instances.items():
                if user.platform == "api":
                    continue  # API 用户不需要保活
                keepalive = KeepAliveManager(base_url, rm_config.get("timeout", 30))
                keepalive.start({user_id: raw_resources.get(user_id, {})})
                _keepalive_managers[user_id] = keepalive

        # 执行 setup hooks
        hooks_config = config.get("hooks", {})
        case_hooks = _get_case_hooks(request.node)

        setup_failed = False
        setup_error = None

        for user_id, user in user_instances.items():
            final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks)
            try:
                _execute_hooks(user, final_hooks.get("setup", []), hook_type="setup")
            except HookFailureError as e:
                setup_failed = True
                setup_error = e
                break  # setup 失障，停止继续执行其他用户的 setup

        if setup_failed:
            # 判断是否是连接类错误（连不上 worker）
            # 连接失败时没必要执行 teardown，只会再等超时
            is_connection_error = False
            if setup_error and setup_error.original_error:
                error_msg = str(setup_error.original_error)
                is_connection_error = any(
                    keyword in error_msg
                    for keyword in ["连接超时", "请求失败", "Connection refused", "无法连接"]
                )

            if not is_connection_error:
                # 非连接错误时，执行 teardown 清理资源
                for user_id, user in user_instances.items():
                    final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks)
                    try:
                        _execute_hooks(user, final_hooks.get("teardown", []), hook_type="teardown")
                    except HookFailureError:
                        pass  # teardown 失障也记录，但不影响流程

            # 停止保活
            for user_id, keepalive in _keepalive_managers.items():
                keepalive.stop()
            _keepalive_managers.clear()

            _generate_report(request, logger, user_instances, force_failed=True, error_msg=str(setup_error))

            # 标记用例失障
            pytest.fail(f"Setup hook 失障: {setup_error}")

        yield user_instances

        # 执行 teardown hooks
        teardown_failed = False
        teardown_error = None

        for user_id, user in user_instances.items():
            final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks)
            try:
                _execute_hooks(user, final_hooks.get("teardown", []), hook_type="teardown")
            except HookFailureError as e:
                teardown_failed = True
                teardown_error = e

        # 停止保活
        for user_id, keepalive in _keepalive_managers.items():
            keepalive.stop()
        _keepalive_managers.clear()

        if teardown_failed:
            _generate_report(request, logger, user_instances, force_failed=True, error_msg=str(teardown_error))
            pytest.fail(f"Teardown hook 失障: {teardown_error}")
        else:
            _generate_report(request, logger, user_instances)


# ── 报告生成 Hook ─────────────────────────────────

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """测试结束后记录结果，用于后续报告生成。"""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        logger = ReportLogger.get_current()

        # 保存测试结果供 fixture teardown 使用
        _test_results[item.nodeid] = {
            "passed": report.passed,
            "failed": report.failed,
            "error_msg": str(report.longrepr) if report.failed else "",
        }

        # 失败时截图
        if report.failed and "users" in item.funcargs:
            users = item.funcargs["users"]

            if logger.is_api_failure():
                # API AW 失败：截所有非 API 用户，放在底部
                for user_id, user in users.items():
                    if user_id.endswith("_api"):
                        continue
                    try:
                        base64_data = user.screenshot()
                        if base64_data:
                            logger.log_screenshot(user_id, base64_data)
                    except Exception:
                        pass
            else:
                # 非 API AW 失败：截所有用户
                for user_id, user in users.items():
                    if user_id.endswith("_api"):
                        continue
                    try:
                        base64_data = user.screenshot()
                        if base64_data:
                            logger.log_screenshot(user_id, base64_data)
                    except Exception:
                        pass

            # 记录错误
            logger.log_error(str(report.longrepr))


# ── 辅助函数 ─────────────────────────────────────────

def _get_case_hooks(node) -> Dict[str, Any]:
    """获取用例级别的 hooks 标记。"""
    marker = node.get_closest_marker("hooks")
    if not marker:
        return {}
    return marker.args[0] if marker.args else marker.kwargs


def _get_namespace(node, config) -> str:
    """获取 namespace，优先级：用例标记 > 目录 conftest > 全局配置。

    Args:
        node: pytest node 对象。
        config: 全局配置字典。

    Returns:
        namespace 字符串。
    """
    # 1. 用例级标记
    marker = node.get_closest_marker("namespace")
    if marker:
        return marker.args[0] if marker.args else marker.kwargs.get("value")

    # 2. 目录级 conftest（向上查找最近的 conftest.py）
    import importlib.util

    test_file_path = Path(node.fspath) if hasattr(node, "fspath") else Path(node.path)
    for parent in test_file_path.parents:
        conftest_path = parent / "conftest.py"
        if conftest_path.exists() and conftest_path != Path(__file__):
            try:
                spec = importlib.util.spec_from_file_location(
                    "dir_conftest", conftest_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "get_namespace"):
                    return module.get_namespace()
            except Exception:
                # 目录 conftest 加载失败，继续向上查找
                continue

    # 3. 全局配置
    return config.get("resource_manager", {}).get("namespace", "default")


def _generate_report(
    request,
    logger: ReportLogger,
    user_instances: Dict[str, User],
    force_failed: bool = False,
    error_msg: str = ""
) -> None:
    """生成测试报告。

    在 fixture teardown 阶段调用，确保 teardown hooks 日志被记录。

    Args:
        request: pytest request 对象。
        logger: 日志收集器。
        user_instances: 用户资源字典。
        force_failed: 强制标记为失障（用于 hook 失障）。
        error_msg: 错误信息（用于 hook 失障）。
    """
    # 获取测试结果
    result = _test_results.get(request.node.nodeid, {"passed": True, "failed": False, "error_msg": ""})

    # hook 失障时，保留原始测试错误，追加 hook 错误
    if force_failed:
        original_error = result.get("error_msg", "")
        if original_error:
            # 有原始测试错误，追加 hook 错误
            result = {
                "passed": False,
                "failed": True,
                "error_msg": original_error + "\n\n--- Hook 错误 ---\n" + error_msg
            }
        else:
            # 无原始错误（如 setup 失障），直接显示 hook 错误
            result = {"passed": False, "failed": True, "error_msg": error_msg}

    # 生成报告（始终在项目根目录下）
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    project_root = Path(__file__).parent  # conftest.py 所在目录即项目根目录
    report_dir = project_root / "report" / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{request.node.name}.html"

    HTMLReportGenerator.generate(
        report_path=report_path,
        case_name=request.node.name,
        case_title=request.instance.__doc__ or "" if hasattr(request, "instance") and request.instance else "",
        logs=logger.get_logs(),
        duration_ms=logger.get_duration(),
        status="passed" if result["passed"] else "failed",
        error_msg=result["error_msg"],
        is_api_failure=logger.is_api_failure()
    )

    # 清理测试结果
    _test_results.pop(request.node.nodeid, None)


def _execute_hooks(user: User, hooks: list, hook_type: str = "setup") -> None:
    """执行 hooks 方法。

    支持两种格式：
    - 字符串: "start_app" - 使用默认参数
    - 字典: {"start_app": "edge"} - 传入参数

    Args:
        user: User 实例。
        hooks: hooks 列表。
        hook_type: hook 类型 ("setup" 或 "teardown")，用于异常信息。

    Raises:
        HookFailureError: hook 执行失障时抛出。
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
                # 忽略连接关闭错误（不影响实际功能）
                import errno
                if isinstance(e, OSError) and e.errno == errno.EPIPE:
                    pass  # Broken pipe，不影响功能
                else:
                    logger.log_error(f"Hook 执行失障 [{hook_name}]: {e}")
                    raise HookFailureError(hook_name, e, hook_type)