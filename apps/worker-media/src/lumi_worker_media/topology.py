from __future__ import annotations

from dataclasses import dataclass

from kombu import Connection, Exchange, Queue

JOBS_EXCHANGE = Exchange("lumi.jobs", type="direct", durable=True)
DOMAIN_EXCHANGE = Exchange("lumi.domain", type="topic", durable=True)
DEAD_LETTER_EXCHANGE = Exchange("lumi.dlx", type="topic", durable=True)


@dataclass(frozen=True, slots=True)
class QueueSpec:
    name: str
    exchange: Exchange
    routing_key: str


QUEUE_SPECS = (
    QueueSpec("lumi.media.image", JOBS_EXCHANGE, "image.transform"),
    QueueSpec("lumi.media.video", JOBS_EXCHANGE, "video.render"),
    QueueSpec("lumi.media.export", JOBS_EXCHANGE, "export.package"),
    QueueSpec("lumi.asset.processing", JOBS_EXCHANGE, "asset.processing"),
)


def build_job_queues() -> tuple[Queue, ...]:
    queues: list[Queue] = []
    for spec in QUEUE_SPECS:
        queue = Queue(
            spec.name,
            exchange=spec.exchange,
            routing_key=spec.routing_key,
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
                "x-dead-letter-routing-key": f"{spec.name}.dead",
            },
        )
        queues.append(queue)
    return tuple(queues)


def build_dlq_queues() -> tuple[Queue, ...]:
    return tuple(
        Queue(
            f"{spec.name}.dlq",
            exchange=DEAD_LETTER_EXCHANGE,
            routing_key=f"{spec.name}.dead",
            durable=True,
        )
        for spec in QUEUE_SPECS
    )


def domain_queue(consumer: str, binding_key: str = "#") -> Queue:
    if not consumer or any(char.isspace() for char in consumer):
        raise ValueError("INVALID_CONSUMER_NAME")
    queue_name = f"lumi.domain.{consumer}"
    return Queue(
        queue_name,
        exchange=DOMAIN_EXCHANGE,
        routing_key=binding_key,
        durable=True,
        queue_arguments={
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
            "x-dead-letter-routing-key": f"{queue_name}.dead",
        },
    )


def domain_dlq(consumer: str) -> Queue:
    queue_name = f"lumi.domain.{consumer}"
    return Queue(
        f"{queue_name}.dlq",
        exchange=DEAD_LETTER_EXCHANGE,
        routing_key=f"{queue_name}.dead",
        durable=True,
    )


def declare_topology(connection: Connection, *, domain_consumers: tuple[str, ...] = ()) -> None:
    with connection.channel() as channel:
        for exchange in (JOBS_EXCHANGE, DOMAIN_EXCHANGE, DEAD_LETTER_EXCHANGE):
            exchange(channel).declare()
        for queue in (*build_job_queues(), *build_dlq_queues()):
            queue(channel).declare()
        for consumer in domain_consumers:
            domain_queue(consumer)(channel).declare()
            domain_dlq(consumer)(channel).declare()
