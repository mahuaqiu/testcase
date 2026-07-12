"""并行任务生命周期单元测试。"""

from unittest.mock import Mock

import pytest

from common.parallel import Action, ParallelContext


def make_action(client):
    return Action(
        action_data={"action_type": "click"},
        platform="web",
        user_id="userA",
        aw_name="DemoAW",
        method="do_click",
        client=client,
    )


def make_batch(client):
    action = make_action(client)
    return {
        "client": client,
        "platform": "web",
        "user_id": "userA",
        "actions": [action.action_data],
        "action_objs": [action],
        "window": None,
    }


def test_lifecycle_accepts_active_states_and_completed(monkeypatch):
    client = Mock()
    client.execute_async.return_value = {"task_id": "task-1"}
    client.get_task.side_effect = [
        {"status": "accepted"},
        {"status": "pending"},
        {"status": "running"},
        {"status": "completed", "actions": [{"status": "success"}]},
    ]
    monkeypatch.setattr("common.parallel.time.sleep", lambda _: None)
    context = ParallelContext(timeout=5)
    result = context._execute_batch_async(make_batch(client), Mock())

    assert result == [{"status": "success"}]
    assert client.get_task.call_count == 4


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("timeout", "超时"),
        ("cancelled", "取消"),
        ("interrupted", "中断"),
    ],
)
def test_lifecycle_maps_failure_terminal_states(status, message):
    client = Mock()
    client.execute_async.return_value = {"task_id": "task-1"}
    client.get_task.return_value = {"status": status}
    context = ParallelContext(timeout=5)

    with pytest.raises(Exception) as caught:
        context._execute_batch_async(make_batch(client), Mock())

    assert message in str(caught.value)


def test_lifecycle_unknown_status_fails_immediately():
    client = Mock()
    client.execute_async.return_value = {"task_id": "task-1"}
    client.get_task.return_value = {"status": "mystery"}
    context = ParallelContext(timeout=5)

    with pytest.raises(Exception) as caught:
        context._execute_batch_async(make_batch(client), Mock())

    assert "未知任务状态" in str(caught.value)
    assert client.get_task.call_count == 1


def test_timeout_uses_deadline_and_requests_cancel(monkeypatch):
    client = Mock()
    client.execute_async.return_value = {"task_id": "task-1"}
    client.get_task.return_value = {"status": "running"}
    clock = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr("common.parallel.time.monotonic", lambda: next(clock))
    context = ParallelContext(timeout=1)

    with pytest.raises(TimeoutError):
        context._execute_batch_async(make_batch(client), Mock(), deadline=1.0)

    client.cancel_task.assert_called_once_with("task-1")
