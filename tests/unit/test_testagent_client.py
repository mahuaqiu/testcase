"""TestagentClient 契约单元测试。"""

from unittest.mock import Mock

import pytest
import requests

from common.testagent_client import TestagentClient as Client, TestagentError as ClientError


def response(status=200, payload=None, text="", headers=None):
    item = Mock()
    item.status_code = status
    item.reason = "Bad Request"
    item.text = text
    item.headers = headers or {}
    item.json.return_value = payload
    return item


def test_execute_async_generates_distinct_idempotency_keys(monkeypatch):
    client = Client()
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return response(payload={"task_id": "task-1", "status": "running"})

    monkeypatch.setattr(client.session, "request", request)
    client.execute_async("web", [])
    client.execute_async("web", [])

    first = calls[0]["headers"]["Idempotency-Key"]
    second = calls[1]["headers"]["Idempotency-Key"]
    assert first
    assert first != second


def test_execute_async_preserves_explicit_key(monkeypatch):
    client = Client()
    request = Mock(return_value=response(payload={"task_id": "task-1"}))
    monkeypatch.setattr(client.session, "request", request)

    client.execute_async("web", [], idempotency_key="fixed-key")

    assert request.call_args.kwargs["headers"] == {"Idempotency-Key": "fixed-key"}


def test_connection_retry_reuses_headers(monkeypatch):
    client = Client()
    first = Mock(side_effect=requests.exceptions.ConnectionError("RemoteDisconnected"))
    retried = Mock(return_value=response(payload={"task_id": "task-1"}))
    original_session = client.session
    original_session.request = first

    class SessionFactory:
        def __init__(self):
            self.headers = {}
            self.request = retried

        def __call__(self):
            return self

    replacement = SessionFactory()
    monkeypatch.setattr("common.testagent_client.requests.Session", replacement)

    result = client.execute_async("web", [], idempotency_key="same-key")

    assert result["task_id"] == "task-1"
    assert client.session is replacement
    assert retried.call_args.kwargs["headers"] == {"Idempotency-Key": "same-key"}


def test_structured_worker_error_is_preserved(monkeypatch):
    client = Client()
    item = response(
        status=409,
        payload={
            "detail": {
                "code": "DEVICE_BUSY",
                "message": "Device/Platform is busy",
                "retryable": True,
                "details": {"busy_task_id": "task-1"},
            }
        },
        headers={"x-request-id": "req-1"},
    )
    monkeypatch.setattr(client.session, "request", Mock(return_value=item))

    with pytest.raises(ClientError) as caught:
        client.execute_async("web", [])

    error = caught.value
    assert str(error) == "Device/Platform is busy"
    assert error.code == "DEVICE_BUSY"
    assert error.retryable is True
    assert error.details == {"busy_task_id": "task-1"}
    assert error.status_code == 409
    assert error.request_id == "req-1"


def test_invalid_success_json_has_stable_code(monkeypatch):
    client = Client()
    item = response(payload=["not", "an", "object"])
    monkeypatch.setattr(client.session, "request", Mock(return_value=item))

    with pytest.raises(ClientError) as caught:
        client.get_task("task-1")

    assert caught.value.code == "INVALID_RESPONSE"
    assert caught.value.retryable is False
