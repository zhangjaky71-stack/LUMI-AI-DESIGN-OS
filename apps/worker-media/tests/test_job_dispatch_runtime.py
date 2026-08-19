from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from lumi_domain.job_dispatch import (
    IMAGE_TRANSFORM_QUEUE,
    IMAGE_TRANSFORM_ROUTING_KEY,
    IMAGE_TRANSFORM_TASK_NAME,
    JOB_DISPATCH_EVENT_NAME,
    JobDispatch,
    JobMessage,
)
from lumi_worker_media.event_runtime import OutboxDispatcher
from lumi_worker_media.job_dispatch_runtime import (
    CeleryJobPublisher,
    MediaJobOutboxDispatcher,
    MediaJobOutboxRecord,
)


def _dispatch() -> JobDispatch:
    return JobDispatch(
        task_name=IMAGE_TRANSFORM_TASK_NAME,
        queue=IMAGE_TRANSFORM_QUEUE,
        message=JobMessage(
            job_id=uuid4(),
            organization_id=uuid4(),
            project_id=uuid4(),
            operation_id=uuid4(),
            trace_id="trace-node-73-1",
        ),
    )


def _row(dispatch: JobDispatch) -> dict[str, object]:
    return {
        "id": uuid4(),
        "organization_id": dispatch.message.organization_id,
        "aggregate_type": "task",
        "aggregate_id": dispatch.message.job_id,
        "schema_version": 1,
        "payload_json": dispatch.as_outbox_payload(),
    }


class FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.exc_type: object | None = None

    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        del exc, traceback
        self.exc_type = exc_type
        self.committed = exc_type is None


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.transaction_state = FakeTransaction()
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return self.transaction_state

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls.append((query, args))
        return self.rows

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    async def close(self) -> None:
        self.closed = True


class RecordingPublisher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[JobDispatch] = []

    def publish(self, dispatch: JobDispatch) -> None:
        self.calls.append(dispatch)
        if self.error is not None:
            raise self.error


def test_media_job_outbox_record_validates_identity_and_route() -> None:
    dispatch = _dispatch()
    row = _row(dispatch)
    record = MediaJobOutboxRecord(
        event_id=row["id"],  # type: ignore[arg-type]
        organization_id=dispatch.message.organization_id,
        aggregate_type="task",
        aggregate_id=dispatch.message.job_id,
        schema_version=1,
        payload=dispatch.as_outbox_payload(),
    )

    assert record.dispatch() == dispatch

    wrong = JobDispatch(
        task_name="lumi.jobs.video.render",
        queue=dispatch.queue,
        message=dispatch.message,
    )
    invalid = MediaJobOutboxRecord(
        event_id=uuid4(),
        organization_id=dispatch.message.organization_id,
        aggregate_type="task",
        aggregate_id=dispatch.message.job_id,
        schema_version=1,
        payload=wrong.as_outbox_payload(),
    )
    with pytest.raises(ValueError, match="MEDIA_JOB_DISPATCH_TASK_NAME_MISMATCH"):
        invalid.dispatch()


def test_job_dispatcher_publishes_only_job_outbox_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = _dispatch()
    connection = FakeConnection([_row(dispatch)])

    async def fake_connect(dsn: str) -> FakeConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr(
        "lumi_worker_media.job_dispatch_runtime.asyncpg.connect",
        fake_connect,
    )
    publisher = RecordingPublisher()
    count = asyncio.run(
        MediaJobOutboxDispatcher("postgresql://test", publisher).dispatch_batch(limit=7)
    )

    assert count == 1
    assert publisher.calls == [dispatch]
    query, args = connection.fetch_calls[0]
    assert "event_name = $2" in query
    assert args == (7, JOB_DISPATCH_EVENT_NAME)
    assert connection.transaction_state.committed is True
    assert connection.closed is True
    assert any("publish_attempts = publish_attempts + 1" in q for q, _ in connection.execute_calls)
    assert any("SET published_at = now()" in q for q, _ in connection.execute_calls)


def test_job_dispatcher_commits_failed_attempt_without_marking_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = _dispatch()
    connection = FakeConnection([_row(dispatch)])

    async def fake_connect(dsn: str) -> FakeConnection:
        del dsn
        return connection

    monkeypatch.setattr(
        "lumi_worker_media.job_dispatch_runtime.asyncpg.connect",
        fake_connect,
    )
    publisher = RecordingPublisher(error=RuntimeError("broker unavailable"))

    with pytest.raises(RuntimeError, match="broker unavailable"):
        asyncio.run(
            MediaJobOutboxDispatcher("postgresql://test", publisher).dispatch_batch()
        )

    assert connection.transaction_state.committed is True
    assert connection.transaction_state.exc_type is None
    assert any("publish_attempts = publish_attempts + 1" in q for q, _ in connection.execute_calls)
    assert not any("SET published_at = now()" in q for q, _ in connection.execute_calls)


def test_domain_outbox_dispatcher_explicitly_excludes_job_dispatch_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection([])

    async def fake_connect(dsn: str) -> FakeConnection:
        del dsn
        return connection

    monkeypatch.setattr("lumi_worker_media.event_runtime.asyncpg.connect", fake_connect)

    class DomainPublisher:
        def publish(self, record: Any) -> None:
            raise AssertionError(f"unexpected publish: {record}")

    count = asyncio.run(
        OutboxDispatcher("postgresql://test", DomainPublisher()).dispatch_batch(limit=5)
    )

    assert count == 0
    query, args = connection.fetch_calls[0]
    assert "event_name <> $2" in query
    assert args == (5, JOB_DISPATCH_EVENT_NAME)


def test_celery_job_publisher_uses_canonical_exchange_queue_and_routing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lumi_worker_media.app as app

    captured: dict[str, object] = {}

    def fake_send_task(task_name: str, *args: object, **kwargs: object) -> object:
        captured["task_name"] = task_name
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(app.celery_app, "send_task", fake_send_task)
    dispatch = _dispatch()
    CeleryJobPublisher().publish(dispatch)

    assert captured["task_name"] == IMAGE_TRANSFORM_TASK_NAME
    options = captured["kwargs"]
    assert isinstance(options, dict)
    assert options["queue"] == IMAGE_TRANSFORM_QUEUE
    assert options["exchange"] == "lumi.jobs"
    assert options["routing_key"] == IMAGE_TRANSFORM_ROUTING_KEY
    assert options["kwargs"] == {}
    assert options["args"] == [dispatch.message.as_dict()]
