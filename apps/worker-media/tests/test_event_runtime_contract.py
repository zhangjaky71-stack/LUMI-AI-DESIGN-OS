from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_worker_media.event_runtime import (
    DeadLetterRecord,
    DeadLetterReplayService,
    EventConsumerRuntime,
    EventValidationError,
    MemoryDeadLetterStore,
    MemoryDomainPublisher,
    MemoryInboxStore,
    MemoryOutboxStore,
    OutboxDispatcher,
    OutboxItem,
    validate_event_envelope,
)
from lumi_worker_media.queue_contracts import ErrorCategory

NOW = datetime(2026, 8, 16, 8, 50, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")
EVENT = UUID("01910000-0000-7000-8000-000000000701")


def project_created() -> dict[str, object]:
    return {
        "spec_version": "lumi.events/1.0",
        "event_id": str(EVENT),
        "event_type": "lumi.project.created.v1",
        "occurred_at": NOW.isoformat(),
        "organization_id": str(ORG),
        "aggregate_type": "project",
        "aggregate_id": str(PROJECT),
        "aggregate_version": 1,
        "producer": "lumi.api",
        "correlation_id": "request-node19",
        "causation_id": None,
        "traceparent": None,
        "payload": {
            "project_id": str(PROJECT),
            "workspace_id": str(WORKSPACE),
            "project_version": 1,
        },
    }


def outbox_item() -> OutboxItem:
    return OutboxItem(
        event_id=EVENT,
        organization_id=ORG,
        event_type="lumi.project.created.v1",
        aggregate_type="project",
        aggregate_id=PROJECT,
        envelope_json=project_created(),
        occurred_at=NOW,
        created_at=NOW,
    )


def test_node12_canonical_envelope_is_accepted() -> None:
    event = validate_event_envelope(project_created())
    assert event.event_id == EVENT
    assert event.partition_key == f"org:{ORG}:aggregate:project:{PROJECT}"


def test_unknown_version_and_extra_payload_fail_closed() -> None:
    value = project_created()
    value["event_type"] = "lumi.project.created.v2"
    with pytest.raises(EventValidationError, match="UNSUPPORTED"):
        validate_event_envelope(value)

    value = project_created()
    payload = dict(value["payload"])
    payload["access_token"] = "forbidden"
    value["payload"] = payload
    with pytest.raises(EventValidationError):
        validate_event_envelope(value)


def test_outbox_row_identity_must_match_immutable_envelope() -> None:
    bad = replace(
        outbox_item(),
        aggregate_id=UUID("01910000-0000-7000-8000-000000000099"),
    )
    with pytest.raises(EventValidationError, match="ROW_MISMATCH"):
        bad.canonical_event()


def test_inbox_duplicate_applies_effect_once() -> None:
    inbox = MemoryInboxStore()
    runtime = EventConsumerRuntime(inbox, consumer="project-indexer.v1")
    effects: list[UUID] = []

    async def handler(event, _connection):
        effects.append(event.event_id)

    first = asyncio.run(runtime.process(project_created(), handler))
    second = asyncio.run(runtime.process(project_created(), handler))
    assert first == "PROCESSED"
    assert second == "DUPLICATE"
    assert effects == [EVENT]


def test_handler_failure_rolls_back_inbox_receipt() -> None:
    inbox = MemoryInboxStore()
    runtime = EventConsumerRuntime(inbox, consumer="project-indexer.v1")
    attempts = 0

    async def handler(_event, _connection):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("effect transaction failed")

    with pytest.raises(RuntimeError):
        asyncio.run(runtime.process(project_created(), handler))
    assert asyncio.run(runtime.process(project_created(), handler)) == "PROCESSED"
    assert attempts == 2


def test_dispatcher_crash_window_can_duplicate_but_inbox_dedupes() -> None:
    store = MemoryOutboxStore((outbox_item(),))
    publisher = MemoryDomainPublisher()
    dispatcher = OutboxDispatcher(store, publisher)
    publisher.fail_after_publish = True
    first = dispatcher.dispatch_batch(ORG, now=NOW)
    assert first.failed == 1
    assert len(publisher.events) == 1

    publisher.fail_after_publish = False
    second = dispatcher.dispatch_batch(ORG, now=NOW + timedelta(seconds=2))
    assert second.published == 1
    assert [event.event_id for event in publisher.events] == [EVENT, EVENT]

    inbox = MemoryInboxStore()
    runtime = EventConsumerRuntime(inbox, consumer="duplicate-proof.v1")
    effects = 0

    async def handler(_event, _connection):
        nonlocal effects
        effects += 1

    for event in publisher.events:
        asyncio.run(runtime.process(event.raw, handler))
    assert effects == 1


def test_dlq_replay_preserves_original_event_identity() -> None:
    store = MemoryDeadLetterStore()
    publisher = MemoryDomainPublisher()
    record_id = UUID("01910000-0000-7000-8000-000000000702")
    record = DeadLetterRecord(
        id=record_id,
        organization_id=ORG,
        message_id=EVENT,
        message_kind="domain_event",
        source_queue="lumi.domain.project-indexer.v1",
        consumer="project-indexer.v1",
        exchange_name="lumi.domain",
        routing_key="lumi.project.created.v1",
        error_category=ErrorCategory.PERMANENT,
        error_code="HANDLER_REJECTED",
        error_message="fixture",
        attempts=3,
        payload=project_created(),
        first_failed_at=NOW,
        last_failed_at=NOW,
    )
    asyncio.run(store.record(record))
    service = DeadLetterReplayService(store=store, publisher=publisher)
    replayed = asyncio.run(service.replay(ORG, record_id, now=NOW + timedelta(minutes=1)))
    assert replayed.replayed_at is not None
    assert len(publisher.raw_messages) == 1
    assert publisher.raw_messages[0][2]["event_id"] == str(EVENT)
    with pytest.raises(ValueError, match="ALREADY_REPLAYED"):
        asyncio.run(service.replay(ORG, record_id, now=NOW + timedelta(minutes=2)))
