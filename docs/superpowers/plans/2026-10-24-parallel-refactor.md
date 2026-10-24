# parallel() 线程级真并行重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `with parallel():` 从"收集原子操作批量提交"重构为"收集调用任务、每用户一线程完整同步执行"，使含取值/分支逻辑的 AW 方法与 API AW 可真正并行。

**Architecture:** `common/parallel.py` 重写为 CallTask（闭包）模型：块内 AW 调用（业务方法/原子操作）由 `aw/base_aw.py` 的两个拦截点包装为 CallTask 入队；退出时按用户分组、每用户一个线程、注入主线程 ReportLogger 后完整同步执行其调用链；首个异常中止该组，全部结束后汇总抛 `ParallelExecutionError`。并行预算通过线程本地 deadline 传导为每个 `/task/execute` 请求的 `config.timeout`（Worker 任务级超时，现有能力）。

**Tech Stack:** Python 3 + pytest + ThreadPoolExecutor + requests。设计文档：`docs/superpowers/specs/2026-10-23-parallel-refactor-design.md`。

## Global Constraints

- Worker（autotest 工程）**零改动**；本计划只改 testcase 工程
- `with parallel(max_workers=10, timeout=300)` 签名与语义不变；`ParallelExecutionError.errors` / `ParallelActionError.action.{user_id,aw_name,method}` / `.original_error` 结构保持
- HTML 报告的格式、样式、分组逻辑（`report_generator.py`、`ReportLogger` 的日志结构）不得改动；仅允许给 `ReportLogger` 新增 `set_current` 类方法
- `testcases/` 目录零改动（架构契约测试 `test_real_testcases_are_not_modified_by_this_change` 强制）
- `PendingResult` / `ParallelModeError` 类定义在 `base_aw.py` 中保留（存量 import 不报错），但执行路径不再返回/抛出
- 所有新代码遵循现有风格：中文 docstring、类型注解、`aw_name/method` 命名
- 测试命令统一从仓库根目录执行：`cd /d/code/testcase && python -m pytest <path> -v`
- 设计文档 4.6 的超时传导公式：`config={"timeout": 剩余预算ms}`；HTTP read_timeout = `max(125, 剩余秒 + 15)`

---

### Task 1: ReportLogger.set_current 注入方法

**Files:**
- Modify: `common/report_logger.py:40-43`（`reset` 类方法之后新增）
- Test: `tests/unit/test_report_logger.py`（追加测试）

**Interfaces:**
- Consumes: 无
- Produces: `ReportLogger.set_current(logger: "ReportLogger") -> None` 类方法——Task 2 的 `_run_group` 依赖它把主线程 logger 注入执行线程

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_report_logger.py` 文件末尾追加（该文件已存在，直接追加；若文件顶部无 `import threading` 则补充）：

```python
def test_set_current_binds_logger_to_current_thread():
    """set_current 将指定 logger 绑定到当前线程（并行线程注入主线程实例）。"""
    import threading

    from common.report_logger import ReportLogger

    main_logger = ReportLogger.get_current()
    seen = {}

    def worker():
        seen["logger"] = ReportLogger.get_current()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    # 子线程默认拿到自己的新实例
    assert seen["logger"] is not main_logger

    def injected_worker():
        ReportLogger.set_current(main_logger)
        seen["injected"] = ReportLogger.get_current()

    thread = threading.Thread(target=injected_worker)
    thread.start()
    thread.join()
    # set_current 注入后子线程拿到主线程实例
    assert seen["injected"] is main_logger
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_report_logger.py::test_set_current_binds_logger_to_current_thread -v`
Expected: FAIL，`AttributeError: type object 'ReportLogger' has no attribute 'set_current'`

- [ ] **Step 3: 实现 set_current**

在 `common/report_logger.py` 的 `reset` 类方法（约 40-43 行）之后新增：

```python
    @classmethod
    def set_current(cls, logger: "ReportLogger") -> None:
        """将指定日志收集器绑定到当前线程。

        并行执行线程通过此方法注入主线程的 logger，
        使子线程的 AW 日志写入同一份报告。

        Args:
            logger: 要绑定的日志收集器实例。
        """
        cls._local.logger = logger
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_report_logger.py -v`
Expected: 全部 PASS（原有测试不受影响）

- [ ] **Step 5: Commit**

```bash
cd /d/code/testcase && git add common/report_logger.py tests/unit/test_report_logger.py && git commit -m "feat(report): ReportLogger 新增 set_current 支持跨线程注入"
```

---

### Task 2: 重写 common/parallel.py（CallTask + 线程执行）

**Files:**
- Modify(全文件重写): `common/parallel.py`
- Delete: `tests/unit/test_parallel_task_lifecycle.py`（测的是被删除的批量任务生命周期）
- Create: `tests/unit/test_parallel_execution.py`

**Interfaces:**
- Consumes: `ReportLogger.get_current/set_current`（Task 1）
- Produces（Task 3/4/5 依赖的精确签名）:
  - `is_collecting() -> bool`、`set_collecting(enabled: bool) -> None`（不变）
  - `get_action_queue() -> Optional[List[CallTask]]`、`set_action_queue(queue) -> None`（队列元素类型变为 CallTask）
  - `set_deadline(deadline: Optional[float]) -> None`、`get_deadline() -> Optional[float]`（新增，线程本地，monotonic 秒）
  - `CallTask` dataclass：`fn: Callable[[], Any]` 必填首位；`user_id/platform/aw_name/method/client` 等字段带默认值（字段名与旧 Action 兼容）
  - `PendingCall(method: str)`：`__bool__/__str__/__repr__/__len__/__iter__/__getitem__/get` 消费即抛 `ParallelCallError`
  - `ParallelActionError(action: CallTask, original_error: Exception)`（结构不变）
  - `ParallelExecutionError(errors)`、`ParallelContext`、`parallel(max_workers, timeout)`（不变）
  - 兼容保留：`Action` dataclass（deprecated 注释，Task 5 删除）——`aw/base_aw.py` 当前仍 `from common.parallel import ... Action`，本任务不动 base_aw

- [ ] **Step 1: 删除旧生命周期测试**

```bash
cd /d/code/testcase && git rm tests/unit/test_parallel_task_lifecycle.py
```

- [ ] **Step 2: 写新机制的失败测试**

创建 `tests/unit/test_parallel_execution.py`：

```python
"""并行执行（线程级真并行）单元测试。"""

import threading
import time

import pytest

from common.parallel import (
    CallTask,
    ParallelActionError,
    ParallelExecutionError,
    ParallelContext,
    PendingCall,
    parallel,
)
from common.report_logger import ReportLogger


def make_task(fn, user_id="userA", method="do_demo", aw_name="DemoAW"):
    return CallTask(fn=fn, user_id=user_id, method=method, aw_name=aw_name)


def test_group_tasks_by_user_preserves_order():
    """同用户任务归入同组且保持声明顺序。"""
    executed = []
    context = ParallelContext()
    context._tasks = [
        make_task(lambda: executed.append("a1"), "userA"),
        make_task(lambda: executed.append("b1"), "userB"),
        make_task(lambda: executed.append("a2"), "userA"),
    ]
    groups = context._group_tasks()
    assert list(groups.keys()) == ["userA", "userB"]
    assert [t.method for t in groups["userA"]] == ["do_demo", "do_demo"]


def test_groups_run_concurrently():
    """不同用户组并发执行（总耗时远小于串行总和）。"""
    started = []
    barrier = threading.Barrier(2, timeout=5)

    def slow():
        started.append(1)
        barrier.wait()  # 两组都到位才放行，串行则超时
        time.sleep(0.05)

    context = ParallelContext()
    context._tasks = [
        make_task(slow, "userA"),
        make_task(slow, "userB"),
    ]
    start = time.monotonic()
    context._execute_parallel()
    elapsed = time.monotonic() - start
    assert len(started) == 2
    assert elapsed < 0.8  # 串行至少 0.2s+屏障超时


def test_same_user_tasks_run_sequentially():
    """同用户多个任务在同一线程按声明顺序执行。"""
    order = []

    context = ParallelContext()
    context._tasks = [
        make_task(lambda: order.append("first"), "userA"),
        make_task(lambda: order.append("second"), "userA"),
        make_task(lambda: order.append("third"), "userA"),
    ]
    context._execute_parallel()
    assert order == ["first", "second", "third"]


def test_first_error_aborts_rest_of_group():
    """组内首个异常中止该组剩余任务，错误精确定位到失败任务。"""
    executed = []

    def boom():
        raise RuntimeError("step2 broken")

    context = ParallelContext()
    context._tasks = [
        make_task(lambda: executed.append("s1"), "userA", method="step1"),
        make_task(boom, "userA", method="step2"),
        make_task(lambda: executed.append("s3"), "userA", method="step3"),
    ]
    context._execute_parallel()

    assert executed == ["s1"]  # step3 未执行
    assert len(context._errors) == 1
    assert context._errors[0].action.method == "step2"
    assert isinstance(context._errors[0].original_error, RuntimeError)


def test_other_group_unaffected_by_failure():
    """某用户失败不影响其它用户执行。"""
    executed = []

    def boom():
        raise RuntimeError("userA broken")

    context = ParallelContext()
    context._tasks = [
        make_task(boom, "userA"),
        make_task(lambda: executed.append("b1"), "userB", method="b1"),
        make_task(lambda: executed.append("b2"), "userB", method="b2"),
    ]
    context._execute_parallel()

    assert executed == ["b1", "b2"]
    assert len(context._errors) == 1
    assert context._errors[0].action.user_id == "userA"


def test_with_block_raises_parallel_execution_error():
    """with 块退出时对失败任务抛 ParallelExecutionError。"""

    def boom():
        raise ValueError("login failed")

    with pytest.raises(ParallelExecutionError) as caught:
        with parallel() as context:
            context._tasks.append(make_task(boom, "userA", method="do_login"))

    assert len(caught.value.errors) == 1
    assert caught.value.errors[0].action.user_id == "userA"
    assert isinstance(caught.value.errors[0].original_error, ValueError)
    assert "do_login" in str(caught.value)


def test_block_exception_skips_execution():
    """块内 Python 异常时不执行已收集任务。"""
    executed = []

    with pytest.raises(ValueError):
        with parallel() as context:
            context._tasks.append(make_task(lambda: executed.append(1)))
            raise ValueError("block error")

    assert executed == []


def test_empty_block_is_noop():
    """空并行块不报错。"""
    with parallel():
        pass


def test_timeout_records_error_and_skips_remaining():
    """预算耗尽：超时组记 TimeoutError，组内未开始任务被跳过。"""
    executed = []

    context = ParallelContext(timeout=0.3)
    context._tasks = [
        make_task(lambda: (time.sleep(0.6), executed.append("slow")), "userA", method="slow"),
        make_task(lambda: executed.append("after"), "userA", method="after"),
    ]
    context._execute_parallel()

    # 主线程按 deadline 放弃等待，记录 TimeoutError
    assert len(context._errors) == 1
    assert "超时" in str(context._errors[0].original_error)

    # 等执行线程自然结束后：slow 已在跑会跑完，after 因 deadline 检查被跳过
    time.sleep(1.0)
    assert executed == ["slow"]


def test_logger_injected_into_worker_thread():
    """执行线程拿到主线程的 ReportLogger 实例。"""
    main_logger = ReportLogger.get_current()
    seen = {}

    context = ParallelContext()
    context._tasks = [
        make_task(lambda: seen.update(logger=ReportLogger.get_current()), "userA"),
    ]
    context._execute_parallel()
    assert seen["logger"] is main_logger


def test_pending_call_raises_on_any_consumption():
    """PendingCall 被消费（bool/str/iter/get）时抛 ParallelCallError。"""
    pending = PendingCall("DemoAW.do_login")

    with pytest.raises(Exception, match="parallel"):
        if pending:
            pass
    with pytest.raises(Exception, match="parallel"):
        str(pending)
    with pytest.raises(Exception, match="parallel"):
        pending.get("actions")
    with pytest.raises(Exception, match="parallel"):
        list(pending)
    # repr 不抛错，便于调试输出
    assert "PendingCall" in repr(pending)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_parallel_execution.py -v`
Expected: FAIL（`ImportError: cannot import name 'CallTask'` 或 `PendingCall`）

- [ ] **Step 4: 全文件重写 common/parallel.py**

用以下内容**完整替换** `common/parallel.py`：

```python
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
    新代码使用 CallTask。
    """

    action_data: Dict[str, Any]
    platform: str
    user_id: str = ""
    aw_name: str = ""
    method: str = ""


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
```

- [ ] **Step 5: 运行新测试确认通过**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_parallel_execution.py -v`
Expected: 11 个测试全部 PASS

- [ ] **Step 6: 验证 base_aw 现有单测与契约测试未受破坏**

Run: `cd /d/code/testcase && python -m pytest tests/unit tests/architecture -v`
Expected: PASS（`base_aw.py` 仍 import 旧 `Action` 类，已在本任务中兼容保留）

- [ ] **Step 7: Commit**

```bash
cd /d/code/testcase && git add common/parallel.py tests/unit/test_parallel_execution.py && git commit -m "refactor(parallel): 重写为 CallTask 线程级并行执行"
```

---

### Task 3: base_aw.py 拦截点改造

**Files:**
- Modify: `aw/base_aw.py`（import 行、`_auto_log_aw_call`、`_execute_with_log`、`_execute_exist_check`、`_exec`、`_exec_bool`）
- Test: Create `tests/unit/test_parallel_interception.py`

**Interfaces:**
- Consumes: `CallTask`、`PendingCall`、`is_collecting`、`get_action_queue`（Task 2）
- Produces:
  - `BaseAW._platform_of_user() -> str`（新私有方法）
  - `BaseAW._execute_sync(method, action_data, log_args, window=None) -> Dict[str, Any]`（现状 `_execute_with_log` 的同步执行体原样迁移，Task 4 将在其中接入超时传导）
  - `BaseAW._execute_exist_sync(method, action_data, log_args, window=None) -> Dict[str, Any]`（现状 `_execute_exist_check` 的同步执行体原样迁移）
  - `_exec` / `_exec_bool` 收集模式下返回 `PendingCall`（替代 `PendingResult`）

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_parallel_interception.py`：

```python
"""AW 拦截点（收集模式）单元测试。"""

from unittest.mock import Mock

import pytest

from aw.base_aw import BaseAW, BaseApiAW
from common.parallel import CallTask, PendingCall, parallel


def make_user(user_id="userA", platform="web"):
    user = Mock()
    user.user_id = user_id
    user.platform = platform
    user.account = "acc"
    user.password = "pwd"
    user.name = "Name"
    user.ip = "127.0.0.1"
    user.device_id = ""
    return user


class DemoAW(BaseAW):
    """含取值/分支逻辑的演示 AW。"""

    PLATFORM = "web"

    def do_login(self):
        """执行登录。"""
        if self.ocr_exist("已登录"):
            return "skip"
        self.ocr_click("登录")
        return "ok"

    def should_see_main(self):
        """断言主界面。"""
        text = self.ocr_get_text()
        assert "会议" in text


class FakeApiAW(BaseApiAW):
    """API AW 演示（继承装饰机制）。"""

    PLATFORM = "api"
    _LOGIN_URL = "https://example.com/login"

    def do_fetch(self):
        """拉取数据。"""
        return {"id": 1}


class NestedAW(BaseAW):
    """内部使用 parallel() 的 AW（嵌套场景）。"""

    PLATFORM = "web"

    def do_double_click(self):
        """并行执行两次点击。"""
        with parallel():
            self.ocr_click("按钮A")
            self.ocr_click("按钮B")


def exist_result(exists):
    output = f'{{"exists": {str(exists).lower()}}}'
    return {"actions": [{"status": "success", "output": output}]}


def click_result():
    return {"actions": [{"status": "success"}]}


def text_result(text):
    import json
    return {"actions": [{"status": "success", "output": json.dumps({"text": text})}]}


def test_business_method_collected_not_executed():
    """收集模式下业务方法不执行，入队为一个 CallTask。"""
    client = Mock()
    aw = DemoAW(client, make_user())

    with parallel() as context:
        result = aw.do_login()

    assert client.execute.call_count == 0  # 收集期不发起请求
    assert len(context._tasks) == 1
    assert context._tasks[0].user_id == "userA"
    assert context._tasks[0].method == "do_login"
    assert isinstance(result, PendingCall)


def test_business_method_executes_after_block():
    """退出块后业务方法在执行线程内真实运行，分支按执行期结果走。"""
    client = Mock()
    client.execute.side_effect = [exist_result(False), click_result()]
    aw = DemoAW(client, make_user())

    with parallel():
        aw.do_login()

    assert client.execute.call_count == 2  # exist=False → 走 ocr_click 分支


def test_branch_takes_other_path_when_exists():
    """分支按执行期真实结果选择（exists=True 时跳过点击）。"""
    client = Mock()
    client.execute.side_effect = [exist_result(True)]
    aw = DemoAW(client, make_user())

    with parallel():
        aw.do_login()

    assert client.execute.call_count == 1  # exist=True → 不点击


def test_should_method_with_get_text_runs_in_parallel():
    """含 ocr_get_text 取值断言的方法可并行执行。"""
    client = Mock()
    client.execute.side_effect = [text_result("我的会议")]
    aw = DemoAW(client, make_user())

    with parallel():
        aw.should_see_main()  # 不抛断言错误即通过

    assert client.execute.call_count == 1


def test_direct_atomic_call_collected():
    """块内直接调原子操作同样入队，退出后执行。"""
    client = Mock()
    client.execute.side_effect = [click_result()]
    aw = DemoAW(client, make_user())

    with parallel() as context:
        aw.ocr_click("登录")

    assert len(context._tasks) == 1
    assert context._tasks[0].method == "ocr_click"
    assert client.execute.call_count == 1


def test_pending_call_error_message():
    """块内消费返回值抛 ParallelCallError 且消息含指引。"""
    client = Mock()
    aw = DemoAW(client, make_user())

    with parallel():
        result = aw.do_login()

    with pytest.raises(Exception, match="封装进 AW 业务方法"):
        if result:
            pass


def test_nested_parallel_inside_aw_method():
    """AW 方法内部的 parallel() 块在执行线程内正常工作（设计 §4.7）。"""
    client = Mock()
    client.execute.side_effect = [click_result(), click_result()]
    aw = NestedAW(client, make_user())

    with parallel() as context:
        aw.do_double_click()

    assert len(context._tasks) == 1          # 外层只收集 do_double_click 一个任务
    assert client.execute.call_count == 2    # 内层块的两个点击在执行线程内执行


def test_api_aw_method_collected_and_runs():
    """API AW 业务方法同样被收集并在退出后执行。"""
    fetched = []
    api_aw = FakeApiAW(None, make_user(user_id="userA_api", platform="api"))

    original = FakeApiAW.do_fetch

    def spy(self):
        value = original(self)
        fetched.append(value)
        return value

    FakeApiAW.do_fetch = spy
    try:
        with parallel() as context:
            api_aw.do_fetch()
    finally:
        FakeApiAW.do_fetch = original

    assert len(context._tasks) == 1
    assert context._tasks[0].user_id == "userA_api"
    assert fetched == [{"id": 1}]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_parallel_interception.py -v`
Expected: FAIL——`test_business_method_collected_not_executed` 失败：收集模式下 `do_login` 的 Python 立即执行，`ocr_exist` 走 `_execute_exist_check` 收集分支返回 None→`_exec_bool` 返回 `PendingResult`，`if PendingResult` 抛 `ParallelModeError`；或 `client.execute.call_count == 0` 断言失败

- [ ] **Step 3: 修改 import 行**

`aw/base_aw.py` 第 13 行：

```python
from common.parallel import is_collecting, get_action_queue, Action
```

替换为：

```python
from common.parallel import (
    CallTask,
    PendingCall,
    get_action_queue,
    is_collecting,
)
```

- [ ] **Step 4: 新增 _platform_of_user 辅助方法**

在 `BaseAW` 类内（`__init__` 之后、`LOG_LEVELS` 之前）新增：

```python
    def _platform_of_user(self) -> str:
        """获取当前生效平台（公共 AW 继承 User 平台）。"""
        platform = self.PLATFORM
        if platform == "common" and self.user:
            platform = self.user.platform
        return platform
```

- [ ] **Step 5: 改造 _auto_log_aw_call 的收集分支**

现状 `wrapper` 的结构是"压栈 → try: if is_collecting(): 执行 func（异常记日志）→ 同步分支 → finally 弹栈"。将收集拦截**提前到压栈之前**。

在 `wrapper` 中，找到（现状 147-159 行）：

```python
        # 从业务调用栈获取父级业务方法（嵌套调用时为外层业务方法）
        call_stack = _business_call_stack()
        parent_frame = call_stack[-1] if call_stack else None
        parent_aw = parent_frame["aw"] if parent_frame else ""
        parent_call_id = parent_frame["call_id"] if parent_frame else ""

        # 生成本次调用的唯一 ID 并压栈（原子操作据此归属分组）
        call_id = uuid.uuid4().hex[:12]
        call_stack.append({
            "call_id": call_id,
            "aw": f"{self._aw_name}.{func.__name__}",
            "display": display_name,
        })
```

在其**之前**（`method_args = {...}` 与用户信息提取之后）插入收集分支，同时用户信息提取上移到压栈前（若现状用户信息在压栈之后，则把 4 行 `user_id/user_account/user_name/user_ip` 赋值移到插入点之前）：

```python
        # 用户信息
        user_id = self.user.user_id if self.user else ""
        user_account = self.user.account if self.user else ""
        user_name = self.user.name if self.user else ""
        user_ip = self.user.ip if self.user else ""

        # 并行收集模式：整个方法延迟到执行线程运行，Python 逻辑不提前执行
        if is_collecting():
            queue = get_action_queue()
            if queue is not None:
                call_stack = _business_call_stack()
                parent_frame = call_stack[-1] if call_stack else None
                queue.append(CallTask(
                    fn=lambda: func(self, *args, **kwargs),
                    platform=self._platform_of_user(),
                    user_id=user_id,
                    user_name=user_name,
                    user_account=user_account,
                    user_ip=user_ip,
                    aw_name=self._aw_name,
                    method=func.__name__,
                    client=self.client,
                    parent_aw=parent_frame["aw"] if parent_frame else "",
                    parent_call_id=parent_frame["call_id"] if parent_frame else "",
                    parent_display=parent_frame["display"] if parent_frame else "",
                ))
                return PendingCall(f"{self._aw_name}.{func.__name__}")
```

然后**删除** wrapper 中原有的整个收集分支（现状 167-214 行 `if is_collecting(): try: return func(...)...` 块），使 `try:` 直接进入同步执行路径（保留原有同步成功/失败日志与 finally 弹栈逻辑不变）。同步分支里原有的用户信息赋值行已上移，删除重复的 4 行赋值。

- [ ] **Step 6: 改造 _execute_with_log（提取 _execute_sync）**

将 `_execute_with_log` 整个方法替换为以下两个方法（`_execute_sync` 的方法体 = 现状 `_execute_with_log` 的同步执行部分，即从 `# 同步执行模式` 注释起到方法结尾，**原样迁移**，仅 docstring 与方法名变化；`platform = self.PLATFORM ... platform = self.user.platform` 两行由 `_platform_of_user()` 替代）：

```python
    def _execute_with_log(
        self,
        method: str,
        action_data: Dict[str, Any],
        log_args: Dict[str, Any],
        window: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行操作并记录日志，失败时抛出异常。

        在 parallel() 上下文中收集为 CallTask，否则立即执行。

        Args:
            method: 方法名。
            action_data: 原始 action 数据（发给服务端）。
            log_args: 用于日志记录的参数。
            window: 窗口定位参数（仅 Windows 平台）。

        Returns:
            执行结果（收集模式下返回 None，由 _exec 包装为 PendingCall）。

        Raises:
            AWError: 执行失败时抛出。
        """
        if is_collecting():
            queue = get_action_queue()
            if queue is not None:
                user_id = self.user.user_id if self.user else ""
                user_name = self.user.name if self.user else ""
                user_account = self.user.account if self.user else ""
                user_ip = self.user.ip if self.user else ""
                parent_aw, parent_call_id, parent_display = self._parent_call_info()
                queue.append(CallTask(
                    fn=lambda: self._execute_sync(
                        method, action_data, log_args, window=window
                    ),
                    platform=self._platform_of_user(),
                    user_id=user_id,
                    user_name=user_name,
                    user_account=user_account,
                    user_ip=user_ip,
                    aw_name=self._aw_name,
                    method=method,
                    client=self.client,
                    parent_aw=parent_aw,
                    window=window,
                    parent_call_id=parent_call_id,
                    parent_display=parent_display,
                ))
                return None  # 收集模式标记，由 _exec 包装为 PendingCall
        return self._execute_sync(method, action_data, log_args, window=window)

    def _execute_sync(
        self,
        method: str,
        action_data: Dict[str, Any],
        log_args: Dict[str, Any],
        window: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """同步执行原子操作并记录日志，失败时抛出 AWError。

        （方法体为原 _execute_with_log 同步执行部分原样迁移：
        开头 platform 计算改为 self._platform_of_user()，
        其余从 "# 同步执行模式" 注释到原方法结尾保持不变。）
        """
        platform = self._platform_of_user()

        # ——以下为原 _execute_with_log 的同步执行部分原样迁移——
        # 自动识别父级业务方法
        parent_aw, parent_call_id, parent_display = self._parent_call_info()
        logger = ReportLogger.get_current()
        start_time = time.time()

        try:
            # ……（现状 468-605 行原样保留：client.execute 调用、
            # 异常日志、结果解析、AWError 抛出，不做任何改动）
```

实施说明（机械操作，无歧义）：将现状 `_execute_with_log` 中 462-605 行（`# 同步执行模式` 注释起到 `return full_result`）剪切为 `_execute_sync` 的方法体，仅做两处改动：
1. 方法体开头的 `platform = self.PLATFORM; if platform == "common" and self.user: platform = self.user.platform` 三行替换为 `platform = self._platform_of_user()`
2. 其余逐行保持不变（包括 `client.execute(platform, [action_data], device_id=device_id, window=window)` 调用——Task 4 才改这一行）

- [ ] **Step 7: 同样改造 _execute_exist_check（提取 _execute_exist_sync）**

与 Step 6 同构：`_execute_exist_check` 的收集分支（现状 994-1020 行）替换为入队 `lambda: self._execute_exist_sync(...)`；同步部分（现状 1022-1111 行）原样迁移为 `_execute_exist_sync`，开头 platform 三行替换为 `platform = self._platform_of_user()`，其余不变（含 `return {"exists": exists}` 结尾）。

`_execute_exist_check` 新收集分支（与 Step 6 的结构相同，fn 与返回值不同）：

```python
        if is_collecting():
            queue = get_action_queue()
            if queue is not None:
                user_id = self.user.user_id if self.user else ""
                user_name = self.user.name if self.user else ""
                user_account = self.user.account if self.user else ""
                user_ip = self.user.ip if self.user else ""
                parent_aw, parent_call_id, parent_display = self._parent_call_info()
                queue.append(CallTask(
                    fn=lambda: self._execute_exist_sync(
                        method, action_data, log_args, window=window
                    ),
                    platform=self._platform_of_user(),
                    user_id=user_id,
                    user_name=user_name,
                    user_account=user_account,
                    user_ip=user_ip,
                    aw_name=self._aw_name,
                    method=method,
                    client=self.client,
                    parent_aw=parent_aw,
                    window=window,
                    parent_call_id=parent_call_id,
                    parent_display=parent_display,
                ))
                return None  # 收集模式标记，由 _exec_bool 包装为 PendingCall
        return self._execute_exist_sync(method, action_data, log_args, window=window)
```

- [ ] **Step 8: _exec / _exec_bool 返回 PendingCall**

现状 `_exec`（1229-1235 行）中：

```python
        result = self._execute_with_log(action_type, full_action_data, log_args, window=window)
        # 收集模式下返回 PendingResult（伪装成 dict）
        if result is None:
            return PendingResult(action_type, "dict")
        return result
```

替换为：

```python
        result = self._execute_with_log(action_type, full_action_data, log_args, window=window)
        # 收集模式下返回 PendingCall，块内消费时抛 ParallelCallError
        if result is None:
            return PendingCall(action_type)
        return result
```

现状 `_exec_bool`（1237-1247 行）中：

```python
        result = self._execute_exist_check(action_type, full_action_data, log_args, window=window)
        # 收集模式下返回 PendingResult
        if result is None:
            return PendingResult(action_type, "bool")
        return result.get("exists", False)
```

替换为：

```python
        result = self._execute_exist_check(action_type, full_action_data, log_args, window=window)
        # 收集模式下返回 PendingCall，块内消费时抛 ParallelCallError
        if result is None:
            return PendingCall(action_type)
        return result.get("exists", False)
```

`PendingResult` / `ParallelModeError` 类定义保留在文件头部不动（存量 import 兼容，执行路径不再引用）。

- [ ] **Step 9: 运行拦截测试确认通过**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_parallel_interception.py -v`
Expected: 8 个测试全部 PASS

- [ ] **Step 10: 运行全量框架测试**

Run: `cd /d/code/testcase && python -m pytest tests/unit tests/architecture -v`
Expected: 全部 PASS

- [ ] **Step 11: Commit**

```bash
cd /d/code/testcase && git add aw/base_aw.py tests/unit/test_parallel_interception.py && git commit -m "refactor(aw): 拦截点上移，业务方法与原子操作收集为 CallTask"
```

---

### Task 4: 超时传导（deadline → config.timeout + read_timeout）

**Files:**
- Modify: `common/testagent_client.py`（`_request`、`execute`）
- Modify: `aw/base_aw.py`（`_execute_sync` 内 client.execute 调用处）
- Test: Create `tests/unit/test_parallel_timeout_budget.py`

**Interfaces:**
- Consumes: `get_deadline()`（Task 2）、`_execute_sync`（Task 3）
- Produces:
  - `TestagentClient._request(method, endpoint, data, params, headers, timeout: Optional[float] = None)`——`timeout` 覆盖 read_timeout（秒），None 用默认
  - `TestagentClient.execute(platform, actions, device_id, user_id, config, level, window, timeout: Optional[float] = None)`——`timeout` 透传 `_request`
  - 行为契约：并行执行（deadline 存在）时每个请求带 `config={"timeout": 剩余ms}` 且 `timeout=max(125, 剩余秒+15)`；非并行时 `config=None, timeout=None`（现状行为）

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_parallel_timeout_budget.py`：

```python
"""并行预算传导（config.timeout / read_timeout）单元测试。"""

import time
from unittest.mock import Mock, patch

import pytest

from aw.base_aw import BaseAW, AWError
from common.parallel import set_deadline
from common.testagent_client import TestagentClient


class BudgetAW(BaseAW):
    """预算传导演示 AW。"""

    PLATFORM = "web"

    def do_click(self):
        """点击操作。"""
        self.ocr_click("登录")


def make_user():
    user = Mock()
    user.user_id = "userA"
    user.platform = "web"
    user.account = "acc"
    user.password = "pwd"
    user.name = "Name"
    user.ip = "127.0.0.1"
    user.device_id = ""
    return user


def ok_result():
    return {"actions": [{"status": "success"}]}


def test_budget_passed_as_config_and_read_timeout():
    """并行执行时请求带剩余预算 config，且 read_timeout 覆盖剩余预算。"""
    client = Mock()
    client.execute.return_value = ok_result()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() + 60)  # 剩余 60s > 125s 缓冲下限? 60+15=75 < 125
        aw.ocr_click("登录")
    finally:
        set_deadline(None)

    _, kwargs = client.execute.call_args
    assert 55000 <= kwargs["config"]["timeout"] <= 60000  # 剩余毫秒
    assert kwargs["timeout"] == 125.0  # max(125, 60+15)


def test_budget_extends_read_timeout_over_default():
    """剩余预算超过默认 read_timeout 时按预算放大。"""
    client = Mock()
    client.execute.return_value = ok_result()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() + 200)  # 200+15=215 > 125
        aw.ocr_click("登录")
    finally:
        set_deadline(None)

    _, kwargs = client.execute.call_args
    assert 190000 <= kwargs["config"]["timeout"] <= 200000
    assert 125.0 < kwargs["timeout"] <= 215.0


def test_no_budget_outside_parallel():
    """非并行执行不带 config 与 timeout（现状行为）。"""
    client = Mock()
    client.execute.return_value = ok_result()
    aw = BudgetAW(client, make_user())

    aw.ocr_click("登录")

    _, kwargs = client.execute.call_args
    assert kwargs["config"] is None
    assert kwargs["timeout"] is None


def test_exhausted_budget_raises_before_request():
    """预算已耗尽时不发请求，直接抛 AWError。"""
    client = Mock()
    aw = BudgetAW(client, make_user())

    try:
        set_deadline(time.monotonic() - 1)  # 已过期
        with pytest.raises(AWError, match="预算已耗尽"):
            aw.ocr_click("登录")
    finally:
        set_deadline(None)

    assert client.execute.call_count == 0


def test_client_request_per_request_timeout():
    """TestagentClient._request 支持单请求覆盖 read_timeout。"""
    client = TestagentClient("http://127.0.0.1:9", connect_timeout=5, read_timeout=10)

    with patch.object(client.session, "request") as request:
        request.side_effect = Exception("stop here")
        with pytest.raises(Exception):
            client._request("POST", "/task/execute", data={}, timeout=42.0)

    _, kwargs = request.call_args
    assert kwargs["timeout"] == (5, 42.0)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_parallel_timeout_budget.py -v`
Expected: FAIL——`client.execute` 不接受 `config`/`timeout` 关键字或未传（`kwargs["config"]` 为 None / TypeError）；`_request` 不接受 `timeout` 参数

- [ ] **Step 3: testagent_client.py 支持单请求超时**

修改 `_request`（现状 144-221 行）——签名与超时计算两处改动，方法体其余逻辑（重试、异常映射）不变：

```python
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求，并在连接中断时复用请求头重试一次。

        Args:
            method: HTTP 方法。
            endpoint: 接口路径。
            data: JSON 请求体。
            params: URL 参数。
            headers: 请求头。
            timeout: 本次请求的读取超时（秒）；None 使用默认 read_timeout。
        """
        url = f"{self.base_url}{endpoint}"
        read_timeout = self.read_timeout if timeout is None else timeout
        request_timeout = (self.connect_timeout, read_timeout)
```

方法体内原 `timeout = (self.connect_timeout, self.read_timeout)` 行删除，`send()` 中 `timeout=timeout` 改为 `timeout=request_timeout`；三个 ReadTimeout 异常消息 `（{self.read_timeout}秒）` 改为 `（{read_timeout}秒）`（首次与重试两处共 4 个字符串）。

修改 `execute`（现状 242-289 行）——签名末尾加 `timeout`，请求体构造后透传：

```python
    def execute(
        self,
        platform: str,
        actions: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        window: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
```

docstring 补充一行：

```python
            timeout: 本次请求的读取超时（秒）；None 使用默认 read_timeout。
```

方法体最后一行：

```python
        return self._request("POST", "/task/execute", data=task_request)
```

替换为：

```python
        return self._request("POST", "/task/execute", data=task_request, timeout=timeout)
```

- [ ] **Step 4: base_aw._execute_sync 接入预算传导**

在 `_execute_sync` 中找到（迁移后的）client.execute 调用处：

```python
            device_id = None
            if platform in PLATFORMS_NEED_DEVICE_ID and self.user:
                device_id = self.user.device_id
            result = self.client.execute(platform, [action_data], device_id=device_id, window=window)
```

替换为：

```python
            device_id = None
            if platform in PLATFORMS_NEED_DEVICE_ID and self.user:
                device_id = self.user.device_id

            # 并行执行时把剩余预算传导给 Worker 任务级 deadline，
            # 并放大 HTTP read_timeout 避免客户端先于 Worker 断连
            deadline = get_deadline()
            config = None
            request_timeout = None
            if deadline is not None:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    raise AWError(f"{self._aw_name}.{method}", {
                        "status": "failed",
                        "error": f"并行预算已耗尽，跳过 {method}",
                    })
                config = {"timeout": remaining_ms}
                request_timeout = max(125.0, (deadline - time.monotonic()) + 15.0)

            result = self.client.execute(
                platform,
                [action_data],
                device_id=device_id,
                window=window,
                config=config,
                timeout=request_timeout,
            )
```

同时确认 `aw/base_aw.py` 顶部 import 行（Task 3 改过的）加入 `get_deadline`：

```python
from common.parallel import (
    CallTask,
    PendingCall,
    get_action_queue,
    get_deadline,
    is_collecting,
)
```

- [ ] **Step 5: 运行预算测试确认通过**

Run: `cd /d/code/testcase && python -m pytest tests/unit/test_parallel_timeout_budget.py -v`
Expected: 5 个测试全部 PASS

- [ ] **Step 6: 运行全量框架测试**

Run: `cd /d/code/testcase && python -m pytest tests/unit tests/architecture -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
cd /d/code/testcase && git add common/testagent_client.py aw/base_aw.py tests/unit/test_parallel_timeout_budget.py && git commit -m "feat(parallel): 并行预算传导为 Worker 任务超时与请求级 read_timeout"
```

---

### Task 5: 清理、架构契约与文档

**Files:**
- Modify: `common/parallel.py`（删除 deprecated `Action` 类）
- Modify: `tests/architecture/test_testcase_contract.py`（追加契约）
- Modify: `AGENTS.md`（第六章重写）
- Modify: `docs/superpowers/specs/2026-10-23-parallel-refactor-design.md`（状态行）

**Interfaces:**
- Consumes: Task 2-4 全部产出
- Produces: 架构契约（parallel 线程级模型不被回退）；面向用例作者的新并行规范文档

- [ ] **Step 1: 写失败的架构契约测试**

在 `tests/architecture/test_testcase_contract.py` 末尾追加：

```python
def test_parallel_uses_thread_level_model():
    """并行块收集调用任务而非原子动作（线程级真并行架构契约）。"""
    parallel_source = (ROOT / "common" / "parallel.py").read_text(encoding="utf-8")
    assert "class CallTask" in parallel_source
    # parallel 路径不再使用批量任务与轮询
    assert "execute_async" not in parallel_source
    assert "get_task" not in parallel_source
    assert "class Action" not in parallel_source  # 旧收集模型已删除

    aw_source = (ROOT / "aw" / "base_aw.py").read_text(encoding="utf-8")
    # 执行路径不再返回 PendingResult（保护由 PendingCall 承担）
    assert "return PendingResult(" not in aw_source
    # 类定义保留（存量 import 兼容）
    assert "class PendingResult" in aw_source
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /d/code/testcase && python -m pytest tests/architecture/test_testcase_contract.py::test_parallel_uses_thread_level_model -v`
Expected: FAIL（`class Action` 仍存在于 parallel.py）

- [ ] **Step 3: 删除 parallel.py 中的 deprecated Action 类**

删除 Task 2 中保留的整个 `Action` dataclass 定义（含 `@dataclass` 装饰器与 `# pragma: no cover - deprecated` 注释块）。全仓 grep 确认无残留引用：

```bash
cd /d/code/testcase && grep -rn "parallel import.*Action\|parallel\.Action" --include="*.py" . | grep -v __pycache__ || echo "no references"
```

Expected: `no references`

- [ ] **Step 4: 重写 AGENTS.md 第六章**

将 AGENTS.md「## 六、并行执行模式」整章（从 `## 六、并行执行模式` 到 `## 七、Hooks 配置` 之前）替换为：

````markdown
## 六、并行执行模式

### 6.1 概述

通过 `parallel()` 上下文管理器实现多用户并行执行：

```python
from common.parallel import parallel

with parallel():
    userA.do_login()
    userB.do_login()
    userC.do_login()
```

**适用场景**：任意 AW 方法（含取值、分支、循环逻辑）在不同用户间并行，
如多用户同时登录、同时入会、同时呼叫，以及 API 用户与 UI 用户混合并发。

### 6.2 工作原理

1. **收集调用**：进入 `with parallel()` 时，块内的 AW 调用（业务方法或
   原子操作）不立即执行，包装为调用任务加入队列
2. **分组执行**：退出上下文时按用户分组，每个用户一个线程完整同步执行
   其调用链——AW 方法内的 `ocr_exist` 判断、`ocr_get_text` 取值等
   Python 逻辑在执行期真实运行，与顺序执行行为一致
3. **结果汇总**：所有用户执行完成后汇总，有失败抛 `ParallelExecutionError`

### 6.3 使用规范

```python
# ✅ 任意 AW 方法可并行，方法内部逻辑自由
with parallel():
    userA.do_login()
    userB.do_check_and_join()   # 内部 if self.ocr_exist(...) 完全可用

# ❌ 唯一禁止点：块内顶层调用的返回值不能在块内消费
with parallel():
    text = userA.ocr_get_text()   # text 此刻不存在，使用时报错

# ✅ 取值逻辑封装进 AW 方法
with parallel():
    userA.do_check_main_page()
```

**规范要点**：
- 并行操作不应有跨用户数据依赖（A 的结果作 B 的输入时分两个块或块外顺序执行）
- 同一用户的多个调用按声明顺序执行
- 合理设置并发数（默认 max_workers=10）与预算（默认 timeout=300 秒）
- 预算耗尽时：未开始的调用跳过，正在执行的操作由 Worker 任务级超时终止

### 6.4 API 说明

```python
from common.parallel import parallel, is_collecting

with parallel(max_workers=5, timeout=60):
    ...
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_workers | int | 10 | 最大并发线程数 |
| timeout | float | 300 | 总预算（秒），传导为每个请求的 Worker 任务级超时 |

### 6.5 基础设施边界

- 每个原子操作独立调用 `/task/execute`，请求携带剩余预算
  （`config.timeout`）；Worker 在预算耗尽处终止任务，未开始的调用跳过
- 同一 Worker 上不同设备（SN）天然并行（设备级资源租约）；
  windows/mac 本机任务互斥；`cmd_exec` 走独立命令域，与平台操作不可
  混在同一任务——并行模式下每次调用独立请求，天然满足
- Worker 的 `detail` 结构化错误由公共客户端解析为 `TestagentError`，
  包含 `code`、`message`、`retryable`、`details`、HTTP 状态码和 `request_id`
- 用例和 AW 不直接处理 Worker 任务生命周期，不根据业务错误的
  `retryable` 属性自动重放动作；传输层重试由基础设施统一处理
- `/ws/screen/{platform}/{device_id}` 的 H.264 推流首帧必须包含解码所需
  配置和可信真实 IDR；Worker 会过滤暖机黑帧/不可独立解码帧，RSM1
  二进制通道和兼容推流协议以 `api.yaml` 为准

### 6.6 异常处理

并行执行失败时抛出 `ParallelExecutionError`，包含所有失败的调用：

```python
from common.parallel import ParallelExecutionError

try:
    with parallel():
        userA.do_login()
        userB.do_login()  # 可能失败
except ParallelExecutionError as e:
    for error in e.errors:
        print(f"{error.action.user_id} 执行失败: {error.original_error}")
```

某用户失败不影响其它用户执行完毕；失败精确定位到用户、AW 类与
原子操作（`action.user_id / aw_name / method`）。
````

- [ ] **Step 5: 更新设计文档状态行**

`docs/superpowers/specs/2026-10-23-parallel-refactor-design.md` 第 3 行 `- 状态：已评审通过` 替换为 `- 状态：已实施`。

- [ ] **Step 6: 全量回归**

Run: `cd /d/code/testcase && python -m pytest tests/unit tests/architecture -v`
Expected: 全部 PASS

同时确认用例目录零改动：

```bash
cd /d/code/testcase && git diff --name-only -- testcases
```

Expected: 无输出

- [ ] **Step 7: Commit**

```bash
cd /d/code/testcase && git add common/parallel.py tests/architecture/test_testcase_contract.py AGENTS.md docs/superpowers/specs/2026-10-23-parallel-refactor-design.md && git commit -m "chore(parallel): 清理旧收集模型，契约测试与文档对齐线程级并行"
```

---

## 验收清单（对照设计文档）

- [ ] 含 `ocr_exist` 分支 / `ocr_get_text` 取值的 AW 方法在 `parallel()` 块内正确执行（设计 §二 目标 1，Task 3）
- [ ] API 用户方法在块内延迟、块外并发执行（设计 §二 目标 2，Task 3）
- [ ] `ParallelExecutionError` 结构与字段兼容（设计 §4.5，Task 2）
- [ ] 报告零改动（全局约束，Task 3 日志走同步路径）
- [ ] 超时传导 `config.timeout` + read_timeout 协调（设计 §4.6，Task 4）
- [ ] 嵌套/空块/块内异常边界行为（设计 §4.7，Task 2）
- [ ] 旧 `PendingResult` 类保留、无执行路径引用（设计 §4.5，Task 5 契约）
- [ ] AGENTS.md 并行规范更新（设计 §七 步骤 4，Task 5）
