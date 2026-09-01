from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

import lumi_worker_media.cli as cli_module
import lumi_worker_media.event_runtime as event_module
import lumi_worker_media.job_dispatch_runtime as dispatch_module
from lumi_worker_media.event_runtime import (
    DomainOutboxHealth,
    OutboxDispatcher,
    OutboxRecord,
)
from lumi_worker_media.job_dispatch_runtime import (
    MediaJobOutboxDispatcher,
    MediaJobOutboxHealth,
)


class _HealthConnection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row

    async def close(self) -> None:
        self.closed = True


class _Publisher:
    def publish(self, dispatch: object) -> None:
        del dispatch


class _DomainPublisher:
    def publish(self, record: OutboxRecord) -> None:
        del record


def test_job_dispatch_health_reads_only_oldest_pending_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _HealthConnection(
        {
            "oldest_unpublished_age_seconds": 321,
            "oldest_publish_attempts": 7,
        }
    )

    async def fake_connect(dsn: str) -> _HealthConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr(dispatch_module.asyncpg, "connect", fake_connect)
    snapshot = asyncio.run(
        MediaJobOutboxDispatcher("postgresql://test", _Publisher()).health_snapshot()
    )

    assert snapshot == MediaJobOutboxHealth(
        oldest_unpublished_age_seconds=321,
        oldest_publish_attempts=7,
    )
    query, args = connection.fetchrow_calls[0]
    assert "ORDER BY created_at, id" in query
    assert "LIMIT 1" in query
    assert "COUNT(" not in query.upper()
    assert "FOR UPDATE" not in query.upper()
    assert "event_name = $1" in query
    assert args == (dispatch_module.JOB_DISPATCH_EVENT_NAME,)
    assert connection.closed is True


def test_domain_dispatch_health_reads_only_oldest_pending_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _HealthConnection(
        {
            "oldest_unpublished_age_seconds": 654,
            "oldest_publish_attempts": 8,
        }
    )

    async def fake_connect(dsn: str) -> _HealthConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr(event_module.asyncpg, "connect", fake_connect)
    snapshot = asyncio.run(
        OutboxDispatcher("postgresql://test", _DomainPublisher()).health_snapshot()
    )

    assert snapshot == DomainOutboxHealth(
        oldest_unpublished_age_seconds=654,
        oldest_publish_attempts=8,
    )
    query, args = connection.fetchrow_calls[0]
    assert "ORDER BY created_at, id" in query
    assert "LIMIT 1" in query
    assert "COUNT(" not in query.upper()
    assert "FOR UPDATE" not in query.upper()
    assert "event_name <> $1" in query
    assert args == (event_module.JOB_DISPATCH_EVENT_NAME,)
    assert connection.closed is True


def test_job_dispatch_health_is_zero_when_queue_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _HealthConnection(None)

    async def fake_connect(dsn: str) -> _HealthConnection:
        del dsn
        return connection

    monkeypatch.setattr(dispatch_module.asyncpg, "connect", fake_connect)
    snapshot = asyncio.run(
        MediaJobOutboxDispatcher("postgresql://test", _Publisher()).health_snapshot()
    )

    assert snapshot.oldest_unpublished_age_seconds == 0
    assert snapshot.oldest_publish_attempts == 0
    assert connection.closed is True


def test_domain_outbox_failed_publish_attempt_commits_before_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = OutboxRecord(
        event_id=uuid4(),
        organization_id=uuid4(),
        event_name="asset.ready",
        aggregate_type="asset",
        aggregate_id=uuid4(),
        schema_version=1,
        payload={"asset_id": str(uuid4())},
        created_at=datetime.now(UTC),
    )

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
        def __init__(self) -> None:
            self.transaction_state = FakeTransaction()
            self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
            self.closed = False

        def transaction(self) -> FakeTransaction:
            return self.transaction_state

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            assert "event_name <> $2" in query
            assert args == (5, event_module.JOB_DISPATCH_EVENT_NAME)
            return [
                {
                    "id": record.event_id,
                    "organization_id": record.organization_id,
                    "event_name": record.event_name,
                    "aggregate_type": record.aggregate_type,
                    "aggregate_id": record.aggregate_id,
                    "schema_version": record.schema_version,
                    "payload_json": record.payload,
                    "created_at": record.created_at,
                }
            ]

        async def execute(self, query: str, *args: object) -> str:
            self.execute_calls.append((query, args))
            return "UPDATE 1"

        async def close(self) -> None:
            self.closed = True

    expected_event_id = record.event_id

    class FailingPublisher:
        def publish(self, record: OutboxRecord) -> None:
            assert record.event_id == expected_event_id
            raise RuntimeError("broker unavailable")

    connection = FakeConnection()

    async def fake_connect(dsn: str) -> FakeConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr(event_module.asyncpg, "connect", fake_connect)

    with pytest.raises(RuntimeError, match="broker unavailable"):
        asyncio.run(
            OutboxDispatcher("postgresql://test", FailingPublisher()).dispatch_batch(limit=5)
        )

    assert connection.transaction_state.committed is True
    assert connection.transaction_state.exc_type is None
    assert any("publish_attempts + 1" in query for query, _ in connection.execute_calls)
    assert not any("published_at = now()" in query for query, _ in connection.execute_calls)
    assert connection.closed is True


def test_dispatch_cli_emits_bounded_combined_json_health_before_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeWakeScheduler:
        def __init__(self, dsn: str) -> None:
            del dsn

        async def stage_due_batch(self, *, limit: int) -> list[object]:
            assert limit == 9
            return []

    class FakeDomainDispatcher:
        def __init__(self, dsn: str, publisher: object) -> None:
            del dsn, publisher

        async def dispatch_batch(self, *, limit: int) -> int:
            assert limit == 9
            return 2

        async def health_snapshot(self) -> DomainOutboxHealth:
            return DomainOutboxHealth(
                oldest_unpublished_age_seconds=701,
                oldest_publish_attempts=9,
            )

    class FakeJobDispatcher:
        def __init__(self, dsn: str, publisher: object) -> None:
            del dsn, publisher

        async def dispatch_batch(self, *, limit: int) -> int:
            assert limit == 9
            raise RuntimeError("postgresql://user:password@private-db.example")

        async def health_snapshot(self) -> MediaJobOutboxHealth:
            return MediaJobOutboxHealth(
                oldest_unpublished_age_seconds=601,
                oldest_publish_attempts=6,
            )

    monkeypatch.setattr(cli_module, "MediaExternalWaitWakeScheduler", FakeWakeScheduler)
    monkeypatch.setattr(cli_module, "OutboxDispatcher", FakeDomainDispatcher)
    monkeypatch.setattr(cli_module, "MediaJobOutboxDispatcher", FakeJobDispatcher)
    monkeypatch.setattr(cli_module, "KombuDomainPublisher", lambda broker_url: broker_url)
    monkeypatch.setattr(cli_module, "CeleryJobPublisher", lambda: object())

    with pytest.raises(RuntimeError, match="OUTBOX_DISPATCH_FAILED:jobs"):
        asyncio.run(
            cli_module._dispatch_outbox(
                "postgresql://test",
                broker_url="amqp://test",
                limit=9,
                watch=False,
                interval=1.0,
            )
        )

    raw = capsys.readouterr().out.strip()
    assert "password" not in raw
    payload = json.loads(raw)
    assert payload == {
        "domain_published": 2,
        "external_wakes": 0,
        "failure_channels": ["jobs"],
        "failure_count": 1,
        "job_published": 0,
        "kind": "lumi.outbox_dispatcher.health",
        "oldest_domain_publish_attempts": 9,
        "oldest_domain_unpublished_age_seconds": 701,
        "oldest_job_publish_attempts": 6,
        "oldest_job_unpublished_age_seconds": 601,
        "oldest_publish_attempts": 9,
        "oldest_unpublished_age_seconds": 701,
        "published": 2,
        "status": "degraded",
    }
