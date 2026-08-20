from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from lumi_domain.performance_events import PerformanceStage, PerformanceTelemetryContext
from lumi_worker_media.job_runtime import TaskJobStore
from lumi_worker_media.queue_contracts import JobMessage, JobState


class FakeConnection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row

    async def close(self) -> None:
        self.closed = True


def _message() -> JobMessage:
    return JobMessage(
        job_id=uuid4(),
        organization_id=uuid4(),
        project_id=uuid4(),
        operation_id=uuid4(),
        trace_id="trace-performance-enqueue",
    )


def _telemetry() -> PerformanceTelemetryContext:
    return PerformanceTelemetryContext(
        performance_run_id="node69-release-run",
        profile_id="A",
        source_rc_sha="a" * 40,
    )


def _patch_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, Any]],
) -> None:
    telemetry = _telemetry()
    monkeypatch.setattr(
        PerformanceTelemetryContext,
        "from_environ",
        classmethod(lambda cls, environ=None: telemetry),
    )

    def fake_emit(context: PerformanceTelemetryContext | None, **kwargs: Any) -> None:
        assert context == telemetry
        events.append(kwargs)

    monkeypatch.setattr("lumi_worker_media.job_runtime.emit_performance_interval", fake_emit)


def test_first_claim_emits_enqueue_from_durable_task_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_at = datetime(2026, 8, 20, 10, 0, 0, 125000, tzinfo=UTC)
    started_at = created_at + timedelta(seconds=1, microseconds=250000)
    connection = FakeConnection(
        {
            "attempt_count": 1,
            "created_at": created_at,
            "started_at": started_at,
            "prior_status": JobState.PENDING.value,
        }
    )

    async def fake_connect(dsn: str) -> FakeConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr("lumi_worker_media.job_runtime.asyncpg.connect", fake_connect)
    events: list[dict[str, Any]] = []
    _patch_telemetry(monkeypatch, events)
    message = _message()

    attempt = asyncio.run(TaskJobStore("postgresql://test").claim(message))

    assert attempt == 1
    assert connection.closed is True
    assert len(events) == 1
    event = events[0]
    assert event["stage"] == PerformanceStage.ENQUEUE
    assert event["service"] == "worker-media"
    assert event["operation_id"] == str(message.operation_id)
    assert event["task_id"] == str(message.job_id)
    assert event["attempt"] == 1
    assert event["completed_at_unix_ns"] - event["started_at_unix_ns"] == 1_250_000_000
    query, args = connection.fetchrow_calls[0]
    assert "candidate.prior_status" in query
    assert "status = 'waiting_external'" in query
    assert "THEN 0 ELSE 1 END" in query
    assert args == (message.job_id, message.organization_id, message.project_id)


def test_retry_claim_does_not_double_count_enqueue_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    connection = FakeConnection(
        {
            "attempt_count": 2,
            "created_at": now - timedelta(seconds=4),
            "started_at": now - timedelta(seconds=3),
            "prior_status": JobState.RETRYING.value,
        }
    )

    async def fake_connect(dsn: str) -> FakeConnection:
        del dsn
        return connection

    monkeypatch.setattr("lumi_worker_media.job_runtime.asyncpg.connect", fake_connect)
    events: list[dict[str, Any]] = []
    _patch_telemetry(monkeypatch, events)

    attempt = asyncio.run(TaskJobStore("postgresql://test").claim(_message()))

    assert attempt == 2
    assert events == []
    assert connection.closed is True


def test_external_wake_does_not_increment_attempt_or_emit_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    connection = FakeConnection(
        {
            "attempt_count": 1,
            "created_at": now - timedelta(minutes=2),
            "started_at": now - timedelta(minutes=2),
            "prior_status": JobState.WAITING_EXTERNAL.value,
        }
    )

    async def fake_connect(dsn: str) -> FakeConnection:
        del dsn
        return connection

    monkeypatch.setattr("lumi_worker_media.job_runtime.asyncpg.connect", fake_connect)
    events: list[dict[str, Any]] = []
    _patch_telemetry(monkeypatch, events)

    attempt = asyncio.run(TaskJobStore("postgresql://test").claim(_message()))

    assert attempt == 1
    assert events == []
    query = connection.fetchrow_calls[0][0]
    assert "status = 'waiting_external'" in query
    assert "retry_not_before IS NULL" in query
    assert "THEN 0 ELSE 1 END" in query


def test_enqueue_lifecycle_rejects_naive_database_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {
            "attempt_count": 1,
            "created_at": datetime(2026, 8, 20, 10, 0),
            "started_at": datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
            "prior_status": JobState.PENDING.value,
        }
    )

    async def fake_connect(dsn: str) -> FakeConnection:
        del dsn
        return connection

    monkeypatch.setattr("lumi_worker_media.job_runtime.asyncpg.connect", fake_connect)
    events: list[dict[str, Any]] = []
    _patch_telemetry(monkeypatch, events)

    with pytest.raises(RuntimeError, match="PERFORMANCE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE"):
        asyncio.run(TaskJobStore("postgresql://test").claim(_message()))

    assert events == []
    assert connection.closed is True
