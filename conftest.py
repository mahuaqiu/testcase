"""
全局 pytest 配置。

提供用户资源管理、hooks 执行、失败截图、报告生成等功能。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import json

from common.config_loader import ConfigLoader
from common.testagent_client import is_retryable_transport_error
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
        "markers",
        "hooks: 用例级 hooks，支持全局/平台/用户。"
        "如 @pytest.mark.hooks(setup=['+login'], userA={'teardown': ['+leave']})",
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

    # exeParam 参数更新全局配置；namespace/env_auth 支持顶层短写。
    if _exe_param:
        cfg = get_config()  # 先加载配置
        _apply_exe_param_overrides(cfg, _exe_param)


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
                device_id=resource.device_id,  # iOS/Android 设备 ID
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
                device_id=resource.device_id,  # API 用户也保留设备信息
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

        # 校验用户键合法性（引用未声明用户时直接 fail）
        try:
            HooksResolver.validate_user_keys(
                case_hooks,
                user_instances.keys(),
                list(hooks_config.keys()),
            )
        except ValueError as e:
            pytest.fail(str(e))

        setup_failed = False
        setup_error = None

        for user_id, user in user_instances.items():
            final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks, user_id=user_id)
            try:
                _execute_hooks(user, final_hooks.get("setup", []), hook_type="setup", user_id=user_id)
            except HookFailureError as e:
                setup_failed = True
                setup_error = e
                break  # setup 失障，停止继续执行其他用户的 setup

        if setup_failed:
            # 判断是否是连接类错误（连不上 worker）
            # 连接失败时没必要执行 teardown，只会再等超时
            is_connection_error = False
            if setup_error and setup_error.original_error:
                is_connection_error = is_retryable_transport_error(setup_error.original_error)

            if not is_connection_error:
                # 非连接错误时，执行 teardown 清理资源
                # teardown 顺序：API 用户优先（数据清理），其它用户顺序执行
                for user_id, user in _sort_users_for_teardown(user_instances):
                    final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks, user_id=user_id)
                    try:
                        _execute_hooks(user, final_hooks.get("teardown", []), hook_type="teardown", user_id=user_id)
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

        # 执行 teardown hooks - 只对实际使用过的用户
        teardown_failed = False
        teardown_error = None

        # teardown 顺序：API 用户优先（数据清理），其它用户顺序执行
        for user_id, user in _sort_users_for_teardown(user_instances):
            # 过滤：跳过未被使用的用户
            if not user._used:
                continue

            final_hooks = HooksResolver.resolve(user.platform, hooks_config, case_hooks, user_id=user_id)
            try:
                _execute_hooks(
                    user, final_hooks.get("teardown", []), hook_type="teardown", user_id=user_id
                )
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

            # 获取已记录截图的用户（避免重复截图）
            users_with_screenshot = set()
            for log_entry in logger.get_logs():
                if log_entry.get("type") == "aw_call" and not log_entry.get("success"):
                    # 检查 result 中的 error_screenshot
                    result = log_entry.get("result", {})
                    error_screenshot = result.get("error_screenshot", "")
                    if error_screenshot and len(error_screenshot) > 100:
                        args = log_entry.get("args", {})
                        user_id = args.get("user_id", "")
                        if user_id:
                            users_with_screenshot.add(user_id)

            # 只对没有截图的用户补充截图
            for user_id, user in users.items():
                if user_id.endswith("_api"):
                    continue
                if user_id in users_with_screenshot:
                    continue  # 已有失败截图，跳过

                try:
                    # Web 平台需要 system 级别截图
                    screenshot_kwargs = {}
                    if user.platform == "web":
                        screenshot_kwargs["level"] = "system"
                    base64_data = user.screenshot(**screenshot_kwargs)
                    if base64_data:
                        logger.log_screenshot(user_id, base64_data)
                except Exception:
                    pass

            # 记录错误
            last_failed = logger.get_last_failed_aw()
            error_user_id = last_failed.get("args", {}).get("user_id", "") if last_failed else ""
            logger.log_error(str(report.longrepr), user_id=error_user_id)
            # 并行失败时拆分每个 action 错误（重要修复）
            if "errors" in locals() and locals()["errors"]:
                for err in locals()["errors"]:
                    if hasattr(err, "action") and err.action:
                        logger.log_error(str(err), user_id=err.action.user_id)


# ── 辅助函数 ─────────────────────────────────────────

def _get_case_hooks(node) -> Dict[str, Any]:
    """获取用例级别的 hooks 标记。"""
    marker = node.get_closest_marker("hooks")
    if not marker:
        return {}
    return marker.args[0] if marker.args else marker.kwargs


def _apply_exe_param_overrides(config: Dict[str, Any], exe_param: Dict[str, Any]) -> None:
    """将 exeParam 覆盖到全局配置。

    ``namespace`` 和 ``env_auth`` 是资源管理配置的常用短参数，支持直接以
    顶层字段传入；同时支持 ``resource_manager`` 嵌套写法。其它字段保持
    原有顶层覆盖行为，嵌套字典使用深度合并，避免覆盖同级默认配置。
    """
    resource_manager = config.setdefault("resource_manager", {})
    for key in ("namespace", "env_auth"):
        if key in exe_param:
            resource_manager[key] = exe_param[key]

    nested_resource_manager = exe_param.get("resource_manager")
    if isinstance(nested_resource_manager, dict):
        ConfigLoader()._deep_merge(resource_manager, nested_resource_manager)

    for key, value in exe_param.items():
        if key not in {"namespace", "env_auth", "resource_manager"}:
            config[key] = value


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

    # 将申请到的用户设备类型传给报告，避免仅依赖 AW 日志推断用户平台。
    # API 用户仅在实际使用过时才写入报告，避免出现“未调用的 userB_api”。
    report_user_details = {}
    for user_id, user in user_instances.items():
        if user.platform == "api" and not getattr(user, "_used", False):
            continue
        report_user_details[user_id] = {
            "name": user.name,
            "ip": user.ip,
            "platform": user.platform,
            # API 用户只用于 HTTP 数据操作，不展示关联 UI 用户的设备类型。
            "display_platform": "" if user.platform == "api" else user.platform,
            "is_api": user.platform == "api",
        }

    HTMLReportGenerator.generate(
        report_path=report_path,
        case_name=request.node.name,
        case_title=request.instance.__doc__ or "" if hasattr(request, "instance") and request.instance else "",
        logs=logger.get_logs(),
        duration_ms=logger.get_duration(),
        status="passed" if result["passed"] else "failed",
        error_msg=result["error_msg"],
        is_api_failure=logger.is_api_failure(),
        user_details=report_user_details,
    )

    # 清理测试结果
    _test_results.pop(request.node.nodeid, None)


def _sort_users_for_teardown(user_instances: Dict[str, User]):
    """teardown 执行顺序排序：API 用户优先，其它用户保持原顺序。

    API 用户通常负责数据清理（如 cancel_all_meetings），需先于 UI 用户的
    stop_app 执行，避免先关闭应用再做数据清理的不合理顺序。

    Args:
        user_instances: 用户资源字典。

    Returns:
        排序后的 (user_id, user) 列表，API 用户在前，其它用户按原顺序在后。
    """
    api_users = [(uid, u) for uid, u in user_instances.items() if u.platform == "api"]
    other_users = [(uid, u) for uid, u in user_instances.items() if u.platform != "api"]
    return api_users + other_users


def _execute_hooks(user: User, hooks: list, hook_type: str = "setup", user_id: Optional[str] = None) -> None:
    """执行 hooks 方法。

    支持两种格式：
    - 字符串: "start_app" - 使用默认参数
    - 字典: {"start_app": "edge"} - 传入参数

    Args:
        user: User 实例。
        hooks: hooks 列表。
        hook_type: hook 类型 ("setup" 或 "teardown")，用于异常信息。
        user_id: 用户ID，用于错误日志跟随用户显示。

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
            logger.log_step(f"执行 hook: {hook_name}" + (f"({hook_arg})" if hook_arg else ""))
            method = getattr(user, method_name)

            # 执行 hook，最多重试 1 次（连接关闭时）
            max_retries = 1
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    _invoke_hook(method, hook_arg)
                    break  # 成功则跳出循环
                except Exception as e:
                    import errno
                    error_msg = str(e)
                    last_error = e

                    # Broken pipe - 不影响功能，不重试
                    if isinstance(e, OSError) and e.errno == errno.EPIPE:
                        break

                    # 传输层连接异常最多重试一次，业务错误不自动重放。
                    is_connection_closed = is_retryable_transport_error(e)

                    if is_connection_closed and attempt < max_retries:
                        # 重试一次，打印日志便于排查
                        logger.log_error(f"Hook [{hook_name}] 连接关闭，正在重试 (attempt {attempt + 1}/{max_retries}): {e}", user_id=user_id)
                        continue

                    # 重试失败或其他错误
                    if is_connection_closed:
                        # 重试后仍失败，记录但不算失障（worker 可能已关闭）
                        logger.log_error(f"Hook [{hook_name}] 连接重试失败: {e}", user_id=user_id)
                        break
                    else:
                        logger.log_error(f"Hook 执行失障 [{hook_name}]: {e}", user_id=user_id)
                        raise HookFailureError(hook_name, e, hook_type)


def _invoke_hook(method, hook_arg) -> None:
    """调用 hook 方法，兼容无参方法使用布尔字典标记的写法。"""
    if hook_arg is None:
        method()
        return

    # 字典格式通常表示一个位置参数；若目标 hook 本身是无参方法，
    # 允许使用 {"hook_name": True} 表示启用该 hook。
    import inspect

    try:
        inspect.signature(method).bind(hook_arg)
    except (TypeError, ValueError):
        method()
    else:
        method(hook_arg)
