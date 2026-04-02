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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from common.report_logger import ReportLogger

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
        aw_name: AW 类名（如 LoginAW）。
        method: 方法名（如 ocr_click）。
        log_args: 用于日志记录的参数字典。
        client: TestagentClient 实例（用于发送请求）。
    """

    action_data: Dict[str, Any]
    platform: str
    user_id: str = ""
    aw_name: str = ""
    method: str = ""
    log_args: Dict[str, Any] = field(default_factory=dict)
    client: Optional["TestagentClient"] = None


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
        """按用户分组，批量异步执行。"""
        if not self._actions:
            return

        logger = ReportLogger.get_current()

        # 1. 按用户分组
        user_batches: Dict[tuple, Dict[str, Any]] = {}
        for action in self._actions:
            # 分组键：(user_id, platform, client)
            key = (action.user_id, action.platform, id(action.client))
            if key not in user_batches:
                user_batches[key] = {
                    "client": action.client,
                    "platform": action.platform,
                    "user_id": action.user_id,
                    "actions": [],      # action_data 列表
                    "action_objs": [],  # Action 对象列表（用于日志）
                }
            user_batches[key]["actions"].append(action.action_data)
            user_batches[key]["action_objs"].append(action)

        # 2. 并行发送异步请求（每个用户一个批量请求）
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures: Dict[Any, Dict[str, Any]] = {}
            for key, batch in user_batches.items():
                future = executor.submit(self._execute_batch_async, batch, logger)
                futures[future] = batch

            # 3. 等待结果
            try:
                for future in as_completed(futures, timeout=self.timeout):
                    batch = futures[future]
                    try:
                        results = future.result()
                        self._results[batch["user_id"]] = results
                    except Exception as e:
                        from aw.base_aw import AWError
                        # 只把真正失败的 action（最后一个执行的）添加到 errors
                        if isinstance(e, AWError):
                            action_results = e.result.get("actions", [])
                            if action_results:
                                # 最后一个 action 是失败的
                                failed_index = len(action_results) - 1
                                if failed_index < len(batch["action_objs"]):
                                    self._errors.append(
                                        ParallelActionError(batch["action_objs"][failed_index], e)
                                    )
                        else:
                            # 其他异常（如连接失败），只记录第一个 action 的错误
                            if batch["action_objs"]:
                                self._errors.append(ParallelActionError(batch["action_objs"][0], e))
            except TimeoutError:
                # 超时处理
                for future, batch in futures.items():
                    if not future.done():
                        future.cancel()
                        for action_obj in batch["action_objs"]:
                            self._errors.append(
                                ParallelActionError(
                                    action_obj, TimeoutError("批量任务执行超时")
                                )
                            )

    def _execute_batch_async(
        self, batch: Dict[str, Any], logger: ReportLogger
    ) -> List[Dict[str, Any]]:
        """执行批量异步请求并轮询结果。

        Worker 逻辑：中间有 action 失败就停止，后续 action 不执行。
        查询结果时：
        - status == "completed": 全部成功
        - status == "failed": 中间有失败，停止执行

        Args:
            batch: 批量数据，包含 client、platform、actions 列表。
            logger: 日志记录器。

        Returns:
            每个 action 的结果列表。

        Raises:
            AWError: 执行失败时抛出。
        """
        from aw.base_aw import AWError

        client = batch["client"]
        platform = batch["platform"]
        actions = batch["actions"]
        action_objs = batch["action_objs"]

        if client is None:
            raise ValueError("client 未设置")

        # 发送异步请求
        async_result = client.execute_async(platform, actions)
        task_id = async_result.get("task_id")

        if not task_id:
            raise ValueError("execute_async 未返回 task_id")

        if not task_id:
            raise ValueError("execute_async 未返回 task_id")

        # 轮询等待结果（2秒一次，最多1分钟）
        max_wait = 60  # 1分钟
        poll_interval = 2  # 2秒
        waited = 0.0

        while waited < max_wait:
            task_result = client.get_task(task_id)

            status = task_result.get("status")

            # worker 返回 'success' 或 'completed' 都表示成功
            if status in ("completed", "success"):
                # 全部成功，记录日志
                action_results = task_result.get("actions", [])
                for i, action_obj in enumerate(action_objs):
                    action_result = action_results[i] if i < len(action_results) else {}
                    self._log_action_result(action_obj, action_result, logger)

                return action_results

            if status == "failed":
                # 中间有失败，只记录已执行的 action 日志（未执行的不记录）
                action_results = task_result.get("actions", [])
                for i, action_result in enumerate(action_results):
                    if i < len(action_objs):
                        self._log_action_result(action_objs[i], action_result, logger)

                # 找到失败的 action（最后一个是失败的）
                failed_action_result = action_results[-1] if action_results else {}
                failed_error = failed_action_result.get("error", "未知错误")
                raise AWError(failed_error, {
                    "task_id": task_id,
                    "failed_action": failed_action_result,
                    "actions": action_results,
                })

            # 继续轮询（pending/running 状态）
            time.sleep(poll_interval)
            waited += poll_interval

        # 超时
        raise TimeoutError(f"批量任务 {task_id} 执行超时（等待超过 {max_wait} 秒）")

    def _log_action_result(
        self,
        action: Action,
        action_result: Dict[str, Any],
        logger: ReportLogger,
    ) -> None:
        """记录单个 action 的执行结果日志。

        Args:
            action: Action 对象。
            action_result: 服务端返回的 action 结果。
            logger: 日志记录器。
        """
        success = action_result.get("status") == "success"

        # 构建完整的 result 字段
        result: Dict[str, Any] = {
            "status": action_result.get("status"),
            "duration_ms": action_result.get("duration_ms", 0),
            "output": action_result.get("output", ""),
            "error": action_result.get("error", ""),
        }

        # 如果有错误截图，添加到 result
        error_screenshot = action_result.get("error_screenshot") or action_result.get("screenshot")
        if error_screenshot:
            result["error_screenshot"] = error_screenshot
        elif not success and action.client:
            # 失败时主动截图（Worker 没有返回截图时）
            try:
                screenshot_result = action.client.screenshot(action.platform)
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
            args={"user_id": action.user_id, **action.log_args},
            success=success,
            result=result,
            duration_ms=action_result.get("duration_ms", 0),
            target_image=target_image_base64,
            target_image_path=target_image_path,
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
        批量任务轮询参数固定为：2秒轮询一次，最多等待60秒。
    """
    return ParallelContext(max_workers=max_workers, timeout=timeout)