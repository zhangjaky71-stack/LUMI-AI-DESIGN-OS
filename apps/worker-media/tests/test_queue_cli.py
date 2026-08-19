from __future__ import annotations

import asyncio

import pytest

from lumi_worker_media import cli


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

    class DomainDispatcher:
        def __init__(self, dsn: str, publisher: object) -> None:
            del dsn, publisher

        async def dispatch_batch(self, *, limit: int) -> int:
            del limit
            calls.append("domain")
            return 2

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
