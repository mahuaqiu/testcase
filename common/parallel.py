"""
并行执行上下文管理器。

提供优雅的多用户并行执行语法：

    with parallel():
        userA.do_login()
        userB.do_login()
        userC.do_login()

工作原理：
1. 进入上下文时，设置全局收集模式
2. AW 方法调用不立即执行，而是构建 Action 对象并收集
3. 退出上下文时，使用 ThreadPoolExecutor 并行执行所有收集的 Action
4. 默认同步执行，向后兼容现有用例
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from common.report_logger import ReportLogger


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

    Attributes:
        aw_name: AW 类名（如 LoginAW）。
        method: 方法名（如 do_login）。
        executor: 执行函数（通常是 client 的某个方法）。
        args: 传递给 executor 的位置参数。
        kwargs: 传递给 executor 的关键字参数。
        user_id: 用户标识（如 userA）。
        log_args: 用于日志记录的参数字典。
    """

    aw_name: str
    method: str
    executor: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    user_id: str = ""
    log_args: Dict[str, Any] = field(default_factory=dict)


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

    收集所有 AW 方法调用，退出时并行执行。

    Args:
        max_workers: 最大并发线程数，默认 10。
        timeout: 总超时时间（秒），默认 300。

    Usage:
        with ParallelContext(max_workers=5) as ctx:
            userA.do_login()
            userB.do_login()
    """

    def __init__(self, max_workers: int = 10, timeout: float = 300):
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

        # 如果有执行错误，抛出第一个
        if self._errors:
            raise ParallelExecutionError(self._errors)

        return False

    def _execute_parallel(self) -> None:
        """并行执行所有收集的动作。"""
        if not self._actions:
            return

        logger = ReportLogger.get_current()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            futures: Dict[Any, Action] = {}
            for action in self._actions:
                future = executor.submit(self._execute_action, action, logger)
                futures[future] = action

            # 等待所有完成
            try:
                for future in as_completed(futures, timeout=self.timeout):
                    action = futures[future]
                    try:
                        result = future.result()
                        self._results[action.user_id] = result
                    except Exception as e:
                        self._errors.append(ParallelActionError(action, e))
            except TimeoutError:
                # 超时处理
                for future, action in futures.items():
                    if not future.done():
                        future.cancel()
                        self._errors.append(
                            ParallelActionError(
                                action, TimeoutError("任务执行超时")
                            )
                        )

    def _execute_action(self, action: Action, logger: ReportLogger) -> Any:
        """执行单个动作并记录日志。

        Args:
            action: 待执行的动作。
            logger: 日志记录器。

        Returns:
            执行结果。

        Raises:
            AWError: 执行失败时抛出。
        """
        from aw.base_aw import AWError  # 导入 AWError

        start_time = time.time()

        try:
            result = action.executor(*action.args, **action.kwargs)
            duration_ms = int((time.time() - start_time) * 1000)

            # 检查执行结果（与 base_aw._execute_with_log 保持一致）
            success = result.get("status") == "success" if isinstance(result, dict) else True

            # 记录日志
            logger.log_aw_call(
                aw_name=action.aw_name,
                method=action.method,
                args={"user_id": action.user_id, **action.log_args},
                success=success,
                result=result if isinstance(result, dict) else {"result": result},
                duration_ms=duration_ms,
            )

            # 失败时抛出异常
            if not success:
                raise AWError(f"{action.aw_name}.{action.method}", result)

            return result
        except AWError:
            # AWError 已经记录了日志，直接抛出
            raise
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # 记录失败日志
            logger.log_aw_call(
                aw_name=action.aw_name,
                method=action.method,
                args={"user_id": action.user_id, **action.log_args},
                success=False,
                result={"error": str(e)},
                duration_ms=duration_ms,
            )
            raise


def parallel(max_workers: int = 10, timeout: float = 300) -> ParallelContext:
    """创建并行执行上下文。

    Args:
        max_workers: 最大并发线程数，默认 10。
        timeout: 总超时时间（秒），默认 300。

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
    """
    return ParallelContext(max_workers=max_workers, timeout=timeout)