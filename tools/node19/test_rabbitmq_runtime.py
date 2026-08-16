from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from kombu import Connection, Producer

from lumi_worker_media.event_runtime import (
    DeadLetterRecord,
    KombuDomainPublisher,
    validate_event_envelope,
)
from lumi_worker_media.job_dlq import KombuJobDeadLetterPublisher
from lumi_worker_media.queue_contracts import ErrorCategory
from lumi_worker_media.topology import (
    JOBS_EXCHANGE,
    build_job_dlq_queues,
    build_job_queues,
    declare_topology,
    domain_queue,
)

BROKER_URL = os.environ["RABBITMQ_URL"]
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")
EVENT = UUID("01910000-0000-7000-8000-000000000811")
JOB = UUID("01910000-0000-7000-8000-000000000812")
DLQ = UUID("01910000-0000-7000-8000-000000000813")


def event_payload() -> dict[str, Any]:
    return {
        "spec_version": "lumi.events/1.0",
        "event_id": str(EVENT),
        "event_type": "lumi.project.created.v1",
        "occurred_at": datetime.now(UTC).isoformat(),
        "organization_id": str(ORG),
        "aggregate_type": "project",
        "aggregate_id": str(PROJECT),
        "aggregate_version": 1,
        "producer": "lumi.node19-smoke",
        "payload": {
            "project_id": str(PROJECT),
            "workspace_id": str(WORKSPACE),
            "project_version": 1,
        },
    }


def job_message_payload() -> dict[str, str]:
    return {
        "job_id": str(JOB),
        "organization_id": str(ORG),
        "project_id": str(PROJECT),
    }


def main() -> None:
    with Connection(BROKER_URL) as connection:
        declare_topology(
            connection,
            domain_consumers=(("node19-smoke.v1", "lumi.project.#"),),
        )

    publisher = KombuDomainPublisher(BROKER_URL)
    publisher.publish(validate_event_envelope(event_payload()))

    with Connection(BROKER_URL) as connection:
        domain = domain_queue("node19-smoke.v1", "lumi.project.#")
        with connection.SimpleQueue(domain) as queue:
            message = queue.get(block=True, timeout=15)
            assert message.payload["event_id"] == str(EVENT)
            message.ack()

        image_queue = next(
            queue for queue in build_job_queues() if queue.name == "lumi.media.image"
        )
        with connection.channel() as channel:
            producer = Producer(channel, serializer="json")
            producer.publish(
                job_message_payload(),
                exchange=JOBS_EXCHANGE,
                routing_key="image.transform",
                serializer="json",
                delivery_mode=2,
                declare=[JOBS_EXCHANGE, image_queue],
            )
        with connection.SimpleQueue(image_queue) as queue:
            message = queue.get(block=True, timeout=15)
            assert message.payload["job_id"] == str(JOB)
            message.ack()

        dlq = next(
            queue
            for queue in build_job_dlq_queues()
            if queue.name == "lumi.media.image.dlq"
        )
        dlq(channel=connection.default_channel).declare()
        failed_at = datetime.now(UTC)
        KombuJobDeadLetterPublisher(BROKER_URL).publish(
            DeadLetterRecord(
                id=DLQ,
                organization_id=ORG,
                message_id=JOB,
                message_kind="job",
                source_queue="lumi.media.image",
                exchange_name="lumi.jobs",
                routing_key="image.transform",
                error_category=ErrorCategory.PERMANENT,
                error_code="INVALID_INPUT",
                error_message="node19 smoke",
                attempts=1,
                payload={
                    "job_kind": "image.transform",
                    "message": job_message_payload(),
                },
                first_failed_at=failed_at,
                last_failed_at=failed_at,
            )
        )
        with connection.SimpleQueue(dlq) as queue:
            message = queue.get(block=True, timeout=15)
            assert message.payload["dead_letter_id"] == str(DLQ)
            assert message.payload["message_id"] == str(JOB)
            assert message.payload["payload"]["job_kind"] == "image.transform"
            message.ack()
    print("NODE19_RABBITMQ_PASS")


if __name__ == "__main__":
    main()
