from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_worker_media.event_runtime import MemoryDeadLetterStore
from lumi_worker_media.job_dlq import (
    JobDeadLetterReplayService,
    JobDeadLetterService,
    MemoryJobDeadLetterPublisher,
)
from lumi_worker_media.queue_contracts import ErrorCategory, JobKind, JobMessage

NOW = datetime(2026, 8, 16, 9, 20, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
JOB = UUID("01910000-0000-7000-8000-000000000831")


class MemorySubmitter:
    def __init__(self) -> None:
        self.calls: list[tuple[JobKind, JobMessage]] = []

    def submit(self, kind: JobKind, message: JobMessage) -> None:
        self.calls.append((kind, message))


def message() -> JobMessage:
    return JobMessage(job_id=JOB, organization_id=ORG, project_id=PROJECT)


def test_permanent_job_failure_is_persisted_and_published_to_dlq() -> None:
    store = MemoryDeadLetterStore()
    publisher = MemoryJobDeadLetterPublisher()
    service = JobDeadLetterService(store=store, publisher=publisher)
    record = asyncio.run(
        service.record_failure(
            kind=JobKind.IMAGE_TRANSFORM,
            message=message(),
            category=ErrorCategory.PERMANENT,
            error_code="INVALID_INPUT",
            error_message="fixture",
            attempts=2,
            now=NOW,
        )
    )
    assert record.id.version == 7
    assert record.message_kind == "job"
    assert record.source_queue == "lumi.media.image"
    assert record.routing_key == "image.transform"
    assert record.payload["job_kind"] == "image.transform"
    assert record.payload["message"]["job_id"] == str(JOB)
    assert publisher.records == [record]
    assert asyncio.run(store.get(ORG, record.id)) == record


def test_job_dlq_replay_uses_submitter_and_preserves_job_identity() -> None:
    store = MemoryDeadLetterStore()
    publisher = MemoryJobDeadLetterPublisher()
    writer = JobDeadLetterService(store=store, publisher=publisher)
    record = asyncio.run(
        writer.record_failure(
            kind=JobKind.ASSET_VALIDATE,
            message=message(),
            category=ErrorCategory.PERMANENT,
            error_code="INVALID_ASSET",
            error_message="fixture",
            attempts=1,
            now=NOW,
        )
    )
    submitter = MemorySubmitter()
    replay = JobDeadLetterReplayService(store=store, submitter=submitter)
    updated = asyncio.run(
        replay.replay(ORG, record.id, now=NOW + timedelta(minutes=1))
    )
    assert updated.replayed_at == NOW + timedelta(minutes=1)
    assert len(submitter.calls) == 1
    kind, replayed_message = submitter.calls[0]
    assert kind is JobKind.ASSET_VALIDATE
    assert replayed_message.job_id == JOB
    assert replayed_message.organization_id == ORG
    with pytest.raises(ValueError, match="ALREADY_REPLAYED"):
        asyncio.run(replay.replay(ORG, record.id, now=NOW + timedelta(minutes=2)))
