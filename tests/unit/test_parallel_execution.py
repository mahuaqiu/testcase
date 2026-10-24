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
