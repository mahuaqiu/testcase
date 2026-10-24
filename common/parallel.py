"""
并行执行上下文管理器（线程级真并行）。

提供优雅的多用户并行执行语法：

    with parallel():
        userA.do_login()
        userB.do_login()

工作原理：
1. 进入上下文时开启收集模式（线程本地）
2. 块内 AW 调用（业务方法/原子操作）不立即执行，包装为 CallTask 入队
3. 退出上下文时按用户分组，每用户一个线程完整同步执行其调用链，
   AW 方法内的取值、分支、循环等 Python 逻辑在执行期真实运行
4. 汇总各组首个异常，有失败抛 ParallelExecutionError
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from common.report_logger import ReportLogger

if TYPE_CHECKING:
    from common.testagent_client import TestagentClient


# ── 全局收集状态（线程本地）────────────────────────────────────

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


def get_action_queue() -> Optional[List["CallTask"]]:
    """获取当前线程的调用任务队列。

    Returns:
        CallTask 列表，如果不在收集模式则返回 None。
    """
    if not is_collecting():
        return None
    return getattr(_collecting_state, "queue", None)


def set_action_queue(queue: Optional[List["CallTask"]]) -> None:
    """设置当前线程的调用任务队列。

    Args:
        queue: CallTask 列表。
    """
    _collecting_state.queue = queue


# ── 并行预算（线程本地）──────────────────────────────────────
# 执行线程内由 ParallelContext 注入截止时间；原子操作执行时读取，
# 用于把剩余预算传导给 Worker（config.timeout）并放大 HTTP read_timeout。

_deadline_state = threading.local()


def set_deadline(deadline: Optional[float]) -> None:
    """设置当前线程的并行预算截止时间。

    Args:
        deadline: time.monotonic() 时间戳（秒）；None 表示非并行执行。
    """
    _deadline_state.deadline = deadline


def get_deadline() -> Optional[float]:
    """获取当前线程的并行预算截止时间。

    Returns:
        截止时间戳，非并行执行时返回 None。
    """
    return getattr(_deadline_state, "deadline", None)


# ── 数据类 ──────────────────────────────────────────────────────


@dataclass
class CallTask:
    """待执行的调用任务。

    fn 为闭包：在执行线程内同步调用，返回真实结果。
    其余字段供 ParallelActionError 定位失败调用（字段名与旧版 Action 兼容）。

    Attributes:
        fn: 闭包，线程内同步执行的真实调用。
        action_data: 兼容占位，恒为 None（不再收集原子动作数据）。
        platform: 平台类型。
        user_id: 用户标识（如 userA）。
        user_name: 用户姓名。
        user_account: 用户账号。
        user_ip: 用户 IP 地址。
        aw_name: AW 类名（如 LoginAW）。
        method: 方法名（如 do_login / ocr_click）。
        log_args: 用于日志记录的参数字典。
        client: TestagentClient 实例。
        parent_aw: 父级业务方法标识（如 LoginAW.do_login），用于日志聚合。
        window: 窗口定位参数（仅 Windows 平台）。
        parent_call_id: 父级业务方法本次调用的唯一 ID（用于报告精确分组）。
        parent_display: 父级业务方法显示名（docstring 首行）。
    """

    fn: Callable[[], Any]
    action_data: Optional[Dict[str, Any]] = None
    platform: str = ""
    user_id: str = ""
    user_name: str = ""
    user_account: str = ""
    user_ip: str = ""
    aw_name: str = ""
    method: str = ""
    log_args: Dict[str, Any] = field(default_factory=dict)
    client: Optional["TestagentClient"] = None
    parent_aw: str = ""
    window: Optional[Dict[str, Any]] = None
    parent_call_id: str = ""
    parent_display: str = ""


@dataclass
class Action:  # pragma: no cover - deprecated
    """已废弃：旧收集模式的原子动作对象。

    仅为本重构过渡期保留（base_aw 改造完成后删除），
    新代码使用 CallTask。字段集与旧版保持一致，
    供 base_aw 过渡期继续构造（Task 3 改造、Task 5 删除）。
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
    parent_aw: str = ""
    window: Optional[Dict[str, Any]] = None
    parent_call_id: str = ""
    parent_display: str = ""


# ── 异常与保护对象 ───────────────────────────────────────────────


class ParallelCallError(Exception):
    """并行块内消费顶层调用返回值的异常。"""

    def __init__(self, method: str, usage: str):
        msg = (
            f"不能在 parallel() 块内使用 {method} 返回值做 {usage}。\n"
            f"原因：块内调用延迟到退出时才执行，返回值不存在。\n"
            f"解决：\n"
            f"  1) 将取值/判断逻辑封装进 AW 业务方法（do_*/should_*）后再并行\n"
            f"  2) 将该调用移到 parallel() 上下文外顺序执行"
        )
        super().__init__(msg)


class PendingCall:
    """并行收集模式下的待定调用占位。

    块内顶层调用的返回值被消费（条件判断、取文本、迭代等）时抛出
    ParallelCallError，提示将逻辑封装进 AW 方法或移出并行块。
    """

    def __init__(self, method: str):
        self._method = method

    def __bool__(self):
        raise ParallelCallError(self._method, "条件判断")

    def __str__(self):
        raise ParallelCallError(self._method, "字符串操作")

    def __repr__(self):
        return f"<PendingCall: {self._method}>"

    def __len__(self):
        raise ParallelCallError(self._method, "列表操作")

    def __iter__(self):
        raise ParallelCallError(self._method, "迭代操作")

    def __getitem__(self, key):
        raise ParallelCallError(self._method, "索引访问")

    def get(self, key, default=None):
        """dict-like get 方法，触发异常提示。"""
        raise ParallelCallError(self._method, "数据访问")


class ParallelActionError(Exception):
    """单个调用执行失败的异常。

    Attributes:
        action: 失败的 CallTask 对象。
        original_error: 原始异常。
    """

    def __init__(self, action: CallTask, original_error: Exception):
        self.action = action
        self.original_error = original_error
        super().__init__(
            f"{action.aw_name}.{action.method} (用户: {action.user_id}) 执行失败: {original_error}"
        )


class ParallelExecutionError(Exception):
    """并行执行失败的异常（多个调用失败）。

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

    收集块内所有 AW 调用为 CallTask，退出时按用户分组，
    每用户一个线程完整同步执行其调用链。

    Args:
        max_workers: 最大并发线程数，默认 10。
        timeout: 总超时时间（秒），默认 300。

    Usage:
        with ParallelContext(max_workers=5):
            userA.do_login()
            userB.do_login()
    """

    def __init__(self, max_workers: int = 10, timeout: float = 300):
        self.max_workers = max_workers
        self.timeout = timeout
        self._tasks: List[CallTask] = []
        self._errors: List[ParallelActionError] = []

    def __enter__(self) -> "ParallelContext":
        """进入上下文，开启收集模式。"""
        set_collecting(True)
        set_action_queue(self._tasks)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """退出上下文，关闭收集模式并并行执行所有调用。"""
        set_collecting(False)
        set_action_queue(None)

        # 块内已有异常（如 Python 错误）时不执行
        if exc_type is not None:
            return False

        self._execute_parallel()

        if self._errors:
            raise ParallelExecutionError(self._errors)

        return False

    # ── 分组与执行 ─────────────────────────────────────────

    def _group_tasks(self) -> Dict[str, List[CallTask]]:
        """按 user_id 分组，组内保持声明顺序。"""
        groups: Dict[str, List[CallTask]] = {}
        for task in self._tasks:
            groups.setdefault(task.user_id or "_anonymous", []).append(task)
        return groups

    def _execute_parallel(self) -> None:
        """按用户分组，每用户一个线程同步执行其调用链。"""
        if not self._tasks:
            return

        groups = self._group_tasks()
        deadline = time.monotonic() + self.timeout
        logger = ReportLogger.get_current()

        executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="parallel"
        )
        futures: Dict[Any, List[CallTask]] = {}
        try:
            for tasks in groups.values():
                future = executor.submit(self._run_group, tasks, logger, deadline)
                futures[future] = tasks

            while futures:
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                done, _ = wait(futures, timeout=remaining)
                if not done:
                    break
                for future in done:
                    tasks = futures.pop(future)
                    try:
                        future.result()
                    except ParallelActionError as error:
                        self._errors.append(error)
                    except Exception as error:
                        # _run_group 自身的基础设施异常，关联到组内首个任务
                        self._errors.append(ParallelActionError(tasks[0], error))

            # 超时未完成的组：记录 TimeoutError，执行线程后台自然结束
            for tasks in futures.values():
                self._errors.append(ParallelActionError(
                    tasks[0],
                    TimeoutError(
                        f"用户 {tasks[0].user_id} 的调用链执行超时"
                        f"（等待超过 {self.timeout} 秒）"
                    ),
                ))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _run_group(self, tasks: List[CallTask], logger, deadline: float) -> None:
        """执行线程函数：同步执行单个用户的调用链。

        首个异常中止该组剩余任务；预算耗尽跳过剩余任务。
        """
        set_collecting(False)
        set_action_queue(None)
        ReportLogger.set_current(logger)
        set_deadline(deadline)
        try:
            for task in tasks:
                if time.monotonic() >= deadline:
                    raise ParallelActionError(
                        task,
                        TimeoutError(
                            f"用户 {task.user_id} 的并行预算已耗尽，"
                            f"跳过 {task.aw_name}.{task.method}"
                        ),
                    )
                try:
                    task.fn()
                except Exception as error:
                    raise ParallelActionError(task, error) from error
        finally:
            set_deadline(None)


def parallel(
    max_workers: int = 10, timeout: float = 300
) -> ParallelContext:
    """创建并行执行上下文。

    Args:
        max_workers: 最大并发线程数，默认 10。
        timeout: 总超时时间（秒），默认 300（所有用户的统一预算）。

    Returns:
        ParallelContext 实例。

    Usage:
        with parallel():
            userA.do_login()
            userB.do_login()

        with parallel(max_workers=5, timeout=60):
            userA.do_login()
            userB.do_login()

    Note:
        块内调用延迟到退出时按用户分组并行执行；并行预算传导为每个
        请求的 Worker 任务级超时（config.timeout）。
    """
    return ParallelContext(max_workers=max_workers, timeout=timeout)
