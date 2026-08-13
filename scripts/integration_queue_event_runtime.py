from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID, uuid4

import asyncpg
from kombu import Connection, Producer

from lumi_worker_media.event_runtime import (
    DeadLetterStore,
    EventConsumerRuntime,
    KombuDomainPublisher,
    KombuEventConsumer,
    OutboxDispatcher,
)
from lumi_worker_media.topology import (
    DOMAIN_EXCHANGE,
    JOBS_EXCHANGE,
    build_job_queues,
    declare_topology,
    domain_dlq,
    domain_queue,
)

CONSUMER = "node19-smoke"


def _dsn() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _noop_handler(connection: asyncpg.Connection, envelope: dict[str, object]) -> None:
    assert connection.is_in_transaction()
    assert envelope["organizationid"]


async def prepare_outbox_event() -> UUID:
    connection = await asyncpg.connect(_dsn())
    try:
        organization_id = await connection.fetchval(
            "SELECT id FROM organizations ORDER BY created_at LIMIT 1"
        )
        if organization_id is None:
            raise RuntimeError("seeded organization required")
        event_id = uuid4()
        asset_id = uuid4()
        payload = {
            "project_id": None,
            "mime_type": "image/png",
            "scanner_status": "CLEAN",
        }
        await connection.execute(
            """
            INSERT INTO outbox_events (
                id, organization_id, event_name, aggregate_type, aggregate_id,
                schema_version, payload_json, publish_attempts, created_at
            ) VALUES ($1,$2,'asset.ready','asset',$3,1,$4::jsonb,0,now())
            """,
            event_id,
            organization_id,
            asset_id,
            json.dumps(payload),
        )
        return event_id
    finally:
        await connection.close()


async def verify_outbox_inbox(broker_url: str) -> None:
    event_id = await prepare_outbox_event()
    dispatcher = OutboxDispatcher(_dsn(), KombuDomainPublisher(broker_url))
    assert await dispatcher.dispatch_batch(limit=10) >= 1

    runtime = EventConsumerRuntime(_dsn(), consumer=CONSUMER)
    queue = domain_queue(CONSUMER, "asset.*")
    with Connection(broker_url) as connection:
        with connection.SimpleQueue(queue) as simple_queue:
            message = simple_queue.get(block=True, timeout=10)
            envelope = message.payload
            assert envelope["id"] == str(event_id)
            assert envelope["data"]["asset_id"]
            assert envelope["data"]["kind"] == "image"
            assert await runtime.process(envelope, _noop_handler) == "PROCESSED"
            assert await runtime.process(envelope, _noop_handler) == "DUPLICATE"
            message.ack()

    # Simulate the classic crash window: publish happened, published_at did not persist.
    connection = await asyncpg.connect(_dsn())
    try:
        await connection.execute(
            "UPDATE outbox_events SET published_at = NULL WHERE id = $1",
            event_id,
        )
    finally:
        await connection.close()
    assert await dispatcher.dispatch_batch(limit=10) >= 1
    with Connection(broker_url) as connection:
        with connection.SimpleQueue(queue) as simple_queue:
            duplicate = simple_queue.get(block=True, timeout=10)
            assert await runtime.process(duplicate.payload, _noop_handler) == "DUPLICATE"
            duplicate.ack()


async def verify_permanent_failure_dlq(broker_url: str) -> None:
    runtime = EventConsumerRuntime(_dsn(), consumer=CONSUMER)
    dead_letters = DeadLetterStore(_dsn())
    adapter = KombuEventConsumer(
        broker_url=broker_url,
        runtime=runtime,
        dead_letters=dead_letters,
        binding_key="invalid.*",
    )
    queue = domain_queue(CONSUMER, "invalid.*")
    invalid = {"id": str(uuid4()), "data": {"bad": True}}
    with Connection(broker_url) as connection:
        with connection.channel() as channel:
            Producer(channel, serializer="json").publish(
                invalid,
                exchange=DOMAIN_EXCHANGE,
                routing_key="invalid.event",
                serializer="json",
                declare=[DOMAIN_EXCHANGE, queue],
            )
    try:
        adapter.consume_one(_noop_handler, timeout=10)
    except Exception:
        pass
    else:
        raise AssertionError("invalid event must fail")

    with Connection(broker_url) as connection:
        with connection.SimpleQueue(domain_dlq(CONSUMER)) as dlq:
            dead = dlq.get(block=True, timeout=10)
            dead.ack()
    connection = await asyncpg.connect(_dsn())
    try:
        count = await connection.fetchval(
            "SELECT count(*) FROM dead_letter_records WHERE consumer = $1",
            CONSUMER,
        )
        assert int(count) >= 1
    finally:
        await connection.close()


def verify_job_queue_separation(broker_url: str) -> None:
    probes = {
        "lumi.media.image": "image.transform",
        "lumi.media.video": "video.render",
        "lumi.media.export": "export.package",
        "lumi.asset.processing": "asset.processing",
    }
    queue_by_name = {queue.name: queue for queue in build_job_queues()}
    with Connection(broker_url) as connection:
        with connection.channel() as channel:
            producer = Producer(channel, serializer="json")
            for queue_name, routing_key in probes.items():
                producer.publish(
                    {"probe": queue_name},
                    exchange=JOBS_EXCHANGE,
                    routing_key=routing_key,
                    serializer="json",
                    declare=[JOBS_EXCHANGE, queue_by_name[queue_name]],
                )
        for queue_name in probes:
            with connection.SimpleQueue(queue_by_name[queue_name]) as queue:
                message = queue.get(block=True, timeout=10)
                assert message.payload == {"probe": queue_name}
                message.ack()


def main() -> int:
    broker_url = os.environ["RABBITMQ_URL"]
    with Connection(broker_url) as connection:
        declare_topology(connection, domain_consumers=(CONSUMER,))
    verify_job_queue_separation(broker_url)
    asyncio.run(verify_outbox_inbox(broker_url))
    asyncio.run(verify_permanent_failure_dlq(broker_url))
    print("NODE-19 live queue/event integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
