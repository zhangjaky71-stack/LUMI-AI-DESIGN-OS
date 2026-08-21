from __future__ import annotations

import asyncio

import pytest

from lumi_worker_media import cli
from lumi_worker_media.event_runtime import DomainOutboxHealth
from lumi_worker_media.job_dispatch_runtime import MediaJobOutboxHealth


def test_domain_dispatch_still_runs_when_job_dispatch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class JobDispatcher:
        def __init__(self, dsn: str, publisher: object) -> None:
            del dsn, publisher

        async def dispatch_batch(self, *, limit: int) -> int:
            del limit
            calls.append("jobs")
            raise RuntimeError("job broker unavailable")

        async def health_snapshot(self) -> MediaJobOutboxHealth:
            return MediaJobOutboxHealth(
                oldest_unpublished_age_seconds=1,
                oldest_publish_attempts=1,
            )

    class DomainDispatcher:
        def __init__(self, dsn: str, publisher: object) -> None:
            del dsn, publisher

        async def dispatch_batch(self, *, limit: int) -> int:
            del limit
            calls.append("domain")
            return 2

        async def health_snapshot(self) -> DomainOutboxHealth:
            return DomainOutboxHealth(
                oldest_unpublished_age_seconds=2,
                oldest_publish_attempts=0,
            )

    monkeypatch.setattr(cli, "MediaJobOutboxDispatcher", JobDispatcher)
    monkeypatch.setattr(cli, "OutboxDispatcher", DomainDispatcher)
    monkeypatch.setattr(cli, "CeleryJobPublisher", lambda: object())
    monkeypatch.setattr(cli, "KombuDomainPublisher", lambda broker_url: object())

    with pytest.raises(RuntimeError, match="OUTBOX_DISPATCH_FAILED:jobs"):
        asyncio.run(
            cli._dispatch_outbox(
                "postgresql://test",
                broker_url="amqp://test",
                limit=10,
                watch=False,
                interval=1.0,
            )
        )

    assert calls == ["jobs", "domain"]
