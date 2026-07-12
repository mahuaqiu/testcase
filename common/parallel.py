"""
并行执行上下文管理器。

提供优雅的多用户并行执行语法：

    with parallel():
        userA.do_login()
        userB.do_login()
        userC.do_login()

工作原理：
1. 进入上下文时，设置全局收集模式
2. AW 方法调用不立即执行，而是收集 action_data
3. 退出上下文时，按用户分组，批量调用 execute_async
4. 轮询 get_task 获取结果，记录日志
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from common.report_logger import ReportLogger

SUCCESS_STATUSES = {"success", "completed"}
ACTIVE_STATUSES = {"accepted", "pending", "running", "cancelling"}
FAILURE_STATUSES = {"failed", "timeout", "cancelled", "interrupted"}
POLL_INTERVAL_SECONDS = 2.0

if TYPE_CHECKING:
    from common.testagent_client import TestagentClient


# ── 全局收集状态（线程安全）────────────────────────────────────

_collecting_state = threading.local()


def is_collecting() -> bool:
    """检查当前线程是否处于收集模式。

    Returns:
        True 如果在 parallel() 上下文中，否则 False。
    """
    return getattr(_collecting_state, "collecting", False)


def set_collecting(enabled: bool) -> None:
    """设置当前线程的收集模式。

    Args:
        enabled: True 开启收集模式，False 关闭。
    """
    _collecting_state.collecting = enabled


def get_action_queue() -> Optional[List["Action"]]:
    """获取当前线程的动作队列。

    Returns:
        动作队列列表，如果不在收集模式则返回 None。
    """
    if not is_collecting():
        return None
    return getattr(_collecting_state, "queue", None)


def set_action_queue(queue: Optional[List["Action"]]) -> None:
    """设置当前线程的动作队列。

    Args:
        queue: 动作队列列表。
    """
    _collecting_state.queue = queue


# ── 数据类 ──────────────────────────────────────────────────────


@dataclass
class Action:
    """待执行的动作。

    收集原始 action_data，用于批量发送给服务端。

    Attributes:
        action_data: 原始 action 数据（发给服务端）。
        platform: 平台类型。
        user_id: 用户标识（如 userA）。
        user_name: 用户姓名。
        user_account: 用户账号。
        user_ip: 用户 IP 地址。
        aw_name: AW 类名（如 LoginAW）。
        method: 方法名（如 ocr_click）。
        log_args: 用于日志记录的参数字典。
        client: TestagentClient 实例（用于发送请求）。
        parent_aw: 父级 AW 标识（如 LoginAW.do_login），用于日志聚合。
        window: 窗口定位参数（仅 Windows 平台，如 {"class": "HwmMainWndClass"}）。
    """

    action_data: Dict[str, Any]
    platform: str
    user_id: str = ""
    user_name: str = ""
    user_account: str = ""
    user_ip: str = ""
    aw_name: str = ""
    method: str = ""
    log_args: Dict[str, Any] = field(default_factory=dict)
    client: Optional["TestagentClient"] = None
    parent_aw: str = ""  # 父级 AW 标识，用于日志聚合
    window: Optional[Dict[str, Any]] = None  # 窗口定位参数（仅 Windows 平台）


# ── 异常类 ───────────────────────────────────────────────────────


class ParallelActionError(Exception):
    """单个动作执行失败的异常。

    Attributes:
        action: 失败的动作对象。
        original_error: 原始异常。
    """

    def __init__(self, action: Action, original_error: Exception):
        self.action = action
        self.original_error = original_error
        super().__init__(
            f"{action.aw_name}.{action.method} (用户: {action.user_id}) 执行失败: {original_error}"
        )


class ParallelExecutionError(Exception):
    """并行执行失败的异常（多个动作失败）。

    Attributes:
        errors: 所有失败的 ParallelActionError 列表。
    """

    def __init__(self, errors: List[ParallelActionError]):
        self.errors = errors
        error_msgs = [str(e) for e in errors]
        super().__init__(
            f"并行执行失败，共 {len(errors)} 个错误:\n" + "\n".join(error_msgs)
        )


# ── 上下文管理器 ─────────────────────────────────────────────────


class ParallelContext:
    """并行执行上下文管理器。

    收集所有 AW 方法调用，退出时按用户分组批量执行。

    Args:
        max_workers: 最大并发线程数，默认 10。
        timeout: 总超时时间（秒），默认 300。

    Usage:
        with ParallelContext(max_workers=5) as ctx:
            userA.do_login()
            userB.do_login()
    """

    def __init__(
        self,
        max_workers: int = 10,
        timeout: float = 300,
    ):
        self.max_workers = max_workers
        self.timeout = timeout
        self._actions: List[Action] = []
        self._results: Dict[str, Any] = {}
        self._errors: List[ParallelActionError] = []

    def __enter__(self) -> "ParallelContext":
        """进入上下文，开启收集模式。"""
        set_collecting(True)
        set_action_queue(self._actions)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """退出上下文，关闭收集模式并执行所有动作。"""
        # 恢复同步模式
        set_collecting(False)
        set_action_queue(None)

        # 如果进入时有异常，不执行
        if exc_type is not None:
            return False

        # 并行执行所有收集的动作
        self._execute_parallel()

        # 如果有执行错误，抛出
        if self._errors:
            raise ParallelExecutionError(self._errors)

        return False

    def _execute_parallel(self) -> None:
        """按用户分组，批量异步执行并共享同一个超时预算。"""
        if not self._actions:
            return

        logger = ReportLogger.get_current()
        user_batches: Dict[tuple, Dict[str, Any]] = {}
        for action in self._actions:
            key = (action.user_id, action.platform, id(action.client))
            if key not in user_batches:
                user_batches[key] = {
                    "client": action.client,
                    "platform": action.platform,
                    "user_id": action.user_id,
                    "actions": [],
                    "action_objs": [],
                    "window": action.window,
                }
            user_batches[key]["actions"].append(action.action_data)
            user_batches[key]["action_objs"].append(action)

        deadline = time.monotonic() + self.timeout
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures: Dict[Any, Dict[str, Any]] = {}
        try:
            for batch in user_batches.values():
                future = executor.submit(self._execute_batch_async, batch, logger, deadline)
                futures[future] = batch

            while futures:
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                done, _ = wait(futures, timeout=remaining)
                if not done:
                    break
                for future in done:
                    batch = futures.pop(future)
                    try:
                        self._results[batch["user_id"]] = future.result()
                    except Exception as error:
                        self._record_batch_error(batch, error)

            if futures:
                for future, batch in list(futures.items()):
                    future.cancel()
                    self._record_batch_error(
                        batch,
                        TimeoutError(f"批量任务执行超时（等待超过 {self.timeout} 秒）"),
                    )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _record_batch_error(self, batch: Dict[str, Any], error: Exception) -> None:
        """将批次异常稳定关联到一个动作，确保错误可定位。"""
        from aw.base_aw import AWError

        action_objs = batch.get("action_objs", [])
        if not action_objs:
            return

        action_index = 0
        if isinstance(error, AWError):
            action_results = error.result.get("actions", [])
            if action_results:
                action_index = min(len(action_results) - 1, len(action_objs) - 1)
        self._errors.append(ParallelActionError(action_objs[action_index], error))

    def _execute_batch_async(
        self,
        batch: Dict[str, Any],
        logger: ReportLogger,
        deadline: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """提交并轮询一个批次，直到成功、失败或截止时间。"""
        from aw.base_aw import AWError

        client = batch["client"]
        platform = batch["platform"]
        actions = batch["actions"]
        action_objs = batch["action_objs"]
        window = batch.get("window")
        if client is None:
            raise ValueError("client 未设置")

        deadline = deadline if deadline is not None else time.monotonic() + self.timeout
        async_result = client.execute_async(platform, actions, window=window)
        task_id = async_result.get("task_id")
        if not task_id:
            raise ValueError("execute_async 未返回 task_id")

        def raise_terminal_error(status: str, task_result: Dict[str, Any]) -> None:
            action_results = task_result.get("actions") or []
            worker_screenshot = task_result.get("error_screenshot", "")
            for index, action_result in enumerate(action_results):
                if index < len(action_objs):
                    is_last = index == len(action_results) - 1
                    self._log_action_result(
                        action_objs[index],
                        action_result,
                        logger,
                        worker_error_screenshot=worker_screenshot if is_last else "",
                    )

            failed_result = action_results[-1] if action_results else {}
            failed_error = (
                failed_result.get("error")
                or task_result.get("error")
                or {
                    "timeout": "批量任务执行超时",
                    "cancelled": "批量任务已取消",
                    "interrupted": "Worker 重启导致任务中断",
                    "failed": "批量任务执行失败",
                }.get(status, f"Worker 返回失败终态: {status}")
            )
            failed_index = min(len(action_results) - 1, len(action_objs) - 1) if action_results else 0
            failed_action = action_objs[failed_index] if action_objs else None
            method_name = (
                f"{failed_action.aw_name}.{failed_action.method}"
                if failed_action
                else "ParallelTask.lifecycle"
            )
            result = {
                "status": status,
                "error": str(failed_error),
                "task_id": task_id,
                "failed_action": failed_result,
                "actions": action_results,
                "error_screenshot": worker_screenshot,
            }
            for key in ("code", "details", "request_id"):
                if key in task_result:
                    result[key] = task_result[key]
            raise AWError(method_name, result)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    client.cancel_task(task_id)
                except Exception:
                    pass
                raise TimeoutError(f"批量任务 {task_id} 执行超时（等待超过 {self.timeout} 秒）")

            task_result = client.get_task(task_id)
            status = task_result.get("status")
            if status in SUCCESS_STATUSES:
                action_results = task_result.get("actions", [])
                for index, action_obj in enumerate(action_objs):
                    action_result = action_results[index] if index < len(action_results) else {}
                    self._log_action_result(action_obj, action_result, logger)
                return action_results
            if status in FAILURE_STATUSES:
                raise_terminal_error(status, task_result)
            if status not in ACTIVE_STATUSES:
                raise AWError(
                    "ParallelTask.lifecycle",
                    {
                        "status": status,
                        "error": f"Worker 返回未知任务状态: {status!r}",
                        "task_id": task_id,
                        "actions": task_result.get("actions", []),
                    },
                )

            sleep_for = min(POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic()))
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _log_action_result(
        self,
        action: Action,
        action_result: Dict[str, Any],
        logger: ReportLogger,
        worker_error_screenshot: str = "",
    ) -> None:
        """记录单个 action 的执行结果日志。

        Args:
            action: Action 对象。
            action_result: 服务端返回的 action 结果。
            logger: 日志记录器。
            worker_error_screenshot: Worker 返回的失败截图（base64）。
        """
        success = action_result.get("status") == "success"

        # 构建完整的 result 字段
        result: Dict[str, Any] = {
            "status": action_result.get("status"),
            "duration_ms": action_result.get("duration_ms", 0),
            "output": action_result.get("output", ""),
            "error": action_result.get("error", ""),
        }

        # 如果有 OCR 信息，添加到 result
        ocr_info = action_result.get("ocr_info")
        if ocr_info:
            result["ocr_info"] = ocr_info

        # 如果有错误截图，添加到 result
        # 优先使用 Worker 返回的 error_screenshot（失败瞬间的截图）
        error_screenshot = worker_error_screenshot or action_result.get("error_screenshot") or action_result.get("screenshot")
        if error_screenshot:
            result["error_screenshot"] = error_screenshot
        elif not success and action.client:
            # Worker 没有返回截图时，手动截图
            # Web 平台需要 system 级别截图（截取原生对话框）
            try:
                screenshot_kwargs = {}
                if action.platform == "web":
                    screenshot_kwargs["level"] = "system"
                screenshot_result = action.client.screenshot(action.platform, **screenshot_kwargs)
                if screenshot_result.get("status") == "success" and screenshot_result.get("actions"):
                    screenshot_data = screenshot_result["actions"][0].get("screenshot") or screenshot_result["actions"][0].get("output", "")
                    if screenshot_data:
                        result["error_screenshot"] = screenshot_data
            except Exception:
                pass  # 截图失败不影响主流程

        # 如果有目标图片路径（image_* 操作），尝试加载
        target_image_base64 = ""
        target_image_path = ""
        if not success and action.method.startswith("image_") and "image_path" in action.log_args:
            from common.utils import load_image_as_base64
            target_image_path = action.log_args["image_path"]
            target_image_base64 = load_image_as_base64(target_image_path) or ""

        logger.log_aw_call(
            aw_name=action.aw_name,
            method=action.method,
            args={"user_id": action.user_id, "user_name": action.user_name, "user_account": action.user_account, "user_ip": action.user_ip, **action.log_args},
            success=success,
            result=result,
            duration_ms=action_result.get("duration_ms", 0),
            target_image=target_image_base64,
            target_image_path=target_image_path,
            parent_aw=action.parent_aw,  # 传递 parent_aw 以支持日志聚合
            request_id=action_result.get("request_id", ""),  # 新增：用于问题定位
        )


def parallel(
    max_workers: int = 10, timeout: float = 300
) -> ParallelContext:
    """创建并行执行上下文。

    Args:
        max_workers: 最大并发线程数，默认 10。
        timeout: 总超时时间（秒），默认 300（用于等待所有用户完成）。

    Returns:
        ParallelContext 实例。

    Usage:
        with parallel():
            userA.do_login()
            userB.do_login()

        # 自定义参数
        with parallel(max_workers=5, timeout=60):
            userA.do_login()
            userB.do_login()

    Note:
        批量任务使用 parallel 的 timeout 作为统一截止时间，默认每2秒轮询一次。
    """
    return ParallelContext(max_workers=max_workers, timeout=timeout)
