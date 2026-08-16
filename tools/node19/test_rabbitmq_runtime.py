from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

from kombu import Connection, Producer

from lumi_worker_media.event_runtime import KombuDomainPublisher, validate_event_envelope
from lumi_worker_media.topology import (
    DEAD_LETTER_EXCHANGE,
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


def event_payload() -> dict[str, object]:
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


def main() -> None:
    declare_topology(
        Connection(BROKER_URL),
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

        image_queue = next(q for q in build_job_queues() if q.name == "lumi.media.image")
        with connection.channel() as channel:
            producer = Producer(channel, serializer="json")
            producer.publish(
                {
                    "job_id": str(JOB),
                    "organization_id": str(ORG),
                    "project_id": str(PROJECT),
                },
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

        dlq = next(q for q in build_job_dlq_queues() if q.name == "lumi.media.image.dlq")
        with connection.channel() as channel:
            producer = Producer(channel, serializer="json")
            producer.publish(
                {"fixture": "dead-letter"},
                exchange=DEAD_LETTER_EXCHANGE,
                routing_key="lumi.media.image.dead",
                serializer="json",
                delivery_mode=2,
                declare=[DEAD_LETTER_EXCHANGE, dlq],
            )
        with connection.SimpleQueue(dlq) as queue:
            message = queue.get(block=True, timeout=15)
            assert message.payload == {"fixture": "dead-letter"}
            message.ack()
    print("NODE19_RABBITMQ_PASS")


if __name__ == "__main__":
    main()
