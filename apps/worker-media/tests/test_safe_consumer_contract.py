from __future__ import annotations

from lumi_worker_media.consumer import SafeKombuEventConsumer
from lumi_worker_media.event_runtime import (
    EventConsumerRuntime,
    MemoryDeadLetterStore,
    MemoryDomainPublisher,
    MemoryInboxStore,
)
from lumi_worker_media.queue_contracts import ErrorCategory
from lumi_worker_media.runtime_ids import new_uuid7


def consumer() -> tuple[SafeKombuEventConsumer, MemoryDomainPublisher]:
    publisher = MemoryDomainPublisher()
    instance = SafeKombuEventConsumer(
        broker_url="memory://",
        runtime=EventConsumerRuntime(MemoryInboxStore(), consumer="safe-consumer.v1"),
        dead_letters=MemoryDeadLetterStore(),
        quarantine_publisher=publisher,
    )
    return instance, publisher


def test_malformed_identity_is_quarantined_instead_of_poison_looping() -> None:
    instance, publisher = consumer()
    instance._record_or_quarantine(
        {"organization_id": "not-a-uuid", "event_id": "also-bad"},
        source_queue="lumi.domain.safe-consumer.v1",
        routing_key="lumi.bad.v1",
        category=ErrorCategory.PERMANENT,
        error_code="EVENT_VALIDATION_FAILED",
        error_message="fixture",
        attempts=1,
    )
    assert len(publisher.raw_messages) == 1
    exchange, routing_key, payload, headers = publisher.raw_messages[0]
    assert exchange == "lumi.dlx"
    assert routing_key.endswith(".dead")
    assert payload["quarantine_reason"] == "INVALID_EVENT_IDENTITY"
    assert headers["lumi-quarantine"] is True


def test_runtime_dead_letter_ids_are_uuid7() -> None:
    assert new_uuid7().version == 7
