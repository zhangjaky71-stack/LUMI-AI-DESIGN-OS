from __future__ import annotations

import asyncio
import json

import pytest

import lumi_worker_media.cli as cli_module
import lumi_worker_media.job_dispatch_runtime as dispatch_module
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
    assert "event_name = $1" in query
    assert args == (dispatch_module.JOB_DISPATCH_EVENT_NAME,)
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


def test_dispatch_cli_emits_bounded_json_health_before_failure(
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
        "oldest_publish_attempts": 6,
        "oldest_unpublished_age_seconds": 601,
        "published": 2,
        "status": "degraded",
    }
