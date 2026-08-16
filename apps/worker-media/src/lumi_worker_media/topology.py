from __future__ import annotations

from dataclasses import dataclass

from kombu import Connection, Exchange, Queue

JOBS_EXCHANGE = Exchange("lumi.jobs", type="direct", durable=True)
DOMAIN_EXCHANGE = Exchange("lumi.domain", type="topic", durable=True)
DEAD_LETTER_EXCHANGE = Exchange("lumi.dlx", type="topic", durable=True)

JOB_QUEUE_MAX_BYTES = 512 * 1024 * 1024
DOMAIN_QUEUE_MAX_BYTES = 256 * 1024 * 1024
DOMAIN_DELIVERY_LIMIT = 8


@dataclass(frozen=True, slots=True)
class QueueSpec:
    name: str
    routing_key: str


JOB_QUEUE_SPECS = (
    QueueSpec("lumi.media.image", "image.transform"),
    QueueSpec("lumi.media.video", "video.render"),
    QueueSpec("lumi.media.export", "export.package"),
    QueueSpec("lumi.asset.processing", "asset.processing"),
)


def build_job_queues() -> tuple[Queue, ...]:
    return tuple(
        Queue(
            spec.name,
            exchange=JOBS_EXCHANGE,
            routing_key=spec.routing_key,
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
                "x-dead-letter-routing-key": f"{spec.name}.dead",
                "x-max-length-bytes": JOB_QUEUE_MAX_BYTES,
                "x-overflow": "reject-publish",
            },
        )
        for spec in JOB_QUEUE_SPECS
    )


def build_job_dlq_queues() -> tuple[Queue, ...]:
    return tuple(
        Queue(
            f"{spec.name}.dlq",
            exchange=DEAD_LETTER_EXCHANGE,
            routing_key=f"{spec.name}.dead",
            durable=True,
        )
        for spec in JOB_QUEUE_SPECS
    )


def _validate_consumer_name(consumer: str) -> None:
    if (
        not consumer
        or len(consumer) > 120
        or not consumer[0].islower()
        or any(not (char.islower() or char.isdigit() or char in "._-") for char in consumer)
    ):
        raise ValueError("INVALID_CONSUMER_NAME")


def domain_queue(consumer: str, binding_key: str = "#") -> Queue:
    _validate_consumer_name(consumer)
    queue_name = f"lumi.domain.{consumer}"
    return Queue(
        queue_name,
        exchange=DOMAIN_EXCHANGE,
        routing_key=binding_key,
        durable=True,
        queue_arguments={
            "x-queue-type": "quorum",
            "x-delivery-limit": DOMAIN_DELIVERY_LIMIT,
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
            "x-dead-letter-routing-key": f"{queue_name}.dead",
            "x-max-length-bytes": DOMAIN_QUEUE_MAX_BYTES,
            "x-overflow": "reject-publish",
        },
    )


def domain_dlq(consumer: str) -> Queue:
    _validate_consumer_name(consumer)
    queue_name = f"lumi.domain.{consumer}"
    return Queue(
        f"{queue_name}.dlq",
        exchange=DEAD_LETTER_EXCHANGE,
        routing_key=f"{queue_name}.dead",
        durable=True,
    )


def declare_topology(
    connection: Connection,
    *,
    domain_consumers: tuple[tuple[str, str], ...] = (),
) -> None:
    with connection.channel() as channel:
        for exchange in (JOBS_EXCHANGE, DOMAIN_EXCHANGE, DEAD_LETTER_EXCHANGE):
            exchange(channel).declare()
        for queue in (*build_job_queues(), *build_job_dlq_queues()):
            queue(channel).declare()
        for consumer, binding_key in domain_consumers:
            domain_queue(consumer, binding_key)(channel).declare()
            domain_dlq(consumer)(channel).declare()
