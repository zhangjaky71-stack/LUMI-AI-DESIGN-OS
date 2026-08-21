from __future__ import annotations

import asyncio
from typing import cast
from uuid import uuid4

import asyncpg
import pytest

import lumi_worker_media.video_generation_repository as repository_module
from lumi_worker_media.video_event_buffer import BufferedVideoEventSink
from lumi_worker_media.video_generation_repository import PostgresVideoRepository


class _RecordingConnection:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        if self.fail:
            raise RuntimeError("database write rejected")
        return "INSERT 0 1"


async def _emit_once(sink: BufferedVideoEventSink) -> None:
    await sink.emit(
        "video_generation.external_wait",
        organization_id=str(uuid4()),
        video_job_id="video-job:test-uow",
        payload={"shot_id": "hero", "attempt": 1},
    )


def test_buffered_video_event_is_idempotent_until_transaction_commit() -> None:
    async def run() -> None:
        organization_id = str(uuid4())
        sink = BufferedVideoEventSink("postgresql://test")
        for _ in range(2):
            await sink.emit(
                "video_generation.external_wait",
                organization_id=organization_id,
                video_job_id="video-job:test-uow",
                payload={"shot_id": "hero", "attempt": 1},
            )
        assert sink.pending_count == 1

        connection = _RecordingConnection()
        await sink.flush_into(cast(asyncpg.Connection, connection))
        assert sink.pending_count == 1
        assert len(connection.calls) == 1
        query, args = connection.calls[0]
        assert "INSERT INTO outbox_events" in query
        assert "ON CONFLICT (id) DO NOTHING" in query
        assert args[2] == "video_generation.external_wait"
        assert '"video_job_id":"video-job:test-uow"' in str(args[4])

        sink.mark_committed()
        assert sink.pending_count == 0

    asyncio.run(run())


def test_buffered_video_event_remains_pending_when_transaction_write_fails() -> None:
    async def run() -> None:
        sink = BufferedVideoEventSink("postgresql://test")
        await _emit_once(sink)
        connection = _RecordingConnection(fail=True)
        with pytest.raises(RuntimeError, match="database write rejected"):
            await sink.flush_into(cast(asyncpg.Connection, connection))
        assert sink.pending_count == 1

    asyncio.run(run())


def test_video_repository_rejects_event_uow_database_mismatch_before_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_connect(dsn: str) -> object:
        raise AssertionError(f"unexpected PostgreSQL connection: {dsn}")

    monkeypatch.setattr(repository_module.asyncpg, "connect", unexpected_connect)
    repository = PostgresVideoRepository("postgresql://database-a")
    sink = BufferedVideoEventSink("postgresql://database-b")

    with pytest.raises(RuntimeError, match="VIDEO_EVENT_UOW_DATABASE_MISMATCH"):
        asyncio.run(
            repository.flush(
                organization_id=str(uuid4()),
                operation_id=str(uuid4()),
                event_sink=sink,
            )
        )
