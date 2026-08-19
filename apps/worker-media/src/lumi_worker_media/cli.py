from __future__ import annotations

import argparse
import asyncio
import os
from uuid import UUID

import asyncpg
from kombu import Connection, Producer

from .event_runtime import KombuDomainPublisher, OutboxDispatcher
from .job_dispatch_runtime import CeleryJobPublisher, MediaJobOutboxDispatcher
from .topology import DOMAIN_EXCHANGE, declare_topology


def main() -> int:
    parser = argparse.ArgumentParser(prog="lumi-queue-runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    topology = sub.add_parser("declare-topology")
    topology.add_argument("--consumer", action="append", default=[])
    dispatch = sub.add_parser("dispatch-outbox")
    dispatch.add_argument("--limit", type=int, default=100)
    dispatch.add_argument("--watch", action="store_true")
    dispatch.add_argument("--interval", type=float, default=1.0)
    replay = sub.add_parser("replay-dead-letter")
    replay.add_argument("--id", required=True)
    args = parser.parse_args()

    broker_url = os.getenv("LUMI_RABBITMQ_URL") or os.getenv("RABBITMQ_URL")
    if not broker_url:
        raise SystemExit("LUMI_RABBITMQ_URL/RABBITMQ_URL is required")
    if args.command == "declare-topology":
        with Connection(broker_url) as connection:
            declare_topology(connection, domain_consumers=tuple(args.consumer))
        return 0
    if args.command == "dispatch-outbox":
        if args.interval <= 0:
            raise SystemExit("--interval must be > 0")
        asyncio.run(
            _dispatch_outbox(
                _database_dsn(),
                broker_url=broker_url,
                limit=args.limit,
                watch=args.watch,
                interval=args.interval,
            )
        )
        return 0
    if args.command == "replay-dead-letter":
        asyncio.run(
            _replay_dead_letter(
                _database_dsn(),
                broker_url=broker_url,
                record_id=UUID(args.id),
            )
        )
        print(f"replayed={args.id}")
        return 0
    raise SystemExit("unknown command")


async def _dispatch_outbox(
    dsn: str,
    *,
    broker_url: str,
    limit: int,
    watch: bool,
    interval: float,
) -> None:
    domain_dispatcher = OutboxDispatcher(dsn, KombuDomainPublisher(broker_url))
    job_dispatcher = MediaJobOutboxDispatcher(dsn, CeleryJobPublisher())
    while True:
        job_published = await job_dispatcher.dispatch_batch(limit=limit)
        domain_published = await domain_dispatcher.dispatch_batch(limit=limit)
        published = job_published + domain_published
        print(
            f"published={published} jobs={job_published} domain={domain_published}"
        )
        if not watch:
            return
        if published == 0:
            await asyncio.sleep(interval)


async def _replay_dead_letter(dsn: str, *, broker_url: str, record_id: UUID) -> None:
    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT id, message_kind, source_queue, routing_key, payload_json, replayed_at
                FROM dead_letter_records
                WHERE id = $1
                FOR UPDATE
                """,
                record_id,
            )
            if row is None:
                raise RuntimeError("DEAD_LETTER_NOT_FOUND")
            if row["replayed_at"] is not None:
                raise RuntimeError("DEAD_LETTER_ALREADY_REPLAYED")
            payload = dict(row["payload_json"])
            if row["message_kind"] == "domain_event":
                await asyncio.to_thread(
                    _publish_domain_replay,
                    broker_url,
                    payload,
                    str(row["routing_key"]),
                )
            elif row["message_kind"] == "job":
                _publish_job_replay(
                    payload,
                    queue=str(row["source_queue"]),
                    routing_key=str(row["routing_key"]),
                )
            else:
                raise RuntimeError("DEAD_LETTER_KIND_INVALID")
            await connection.execute(
                """
                UPDATE dead_letter_records
                SET replayed_at = now(), updated_at = now(), version = version + 1
                WHERE id = $1
                """,
                record_id,
            )
    finally:
        await connection.close()


def _publish_domain_replay(broker_url: str, payload: dict[str, object], routing_key: str) -> None:
    with Connection(broker_url) as connection:
        with connection.channel() as channel:
            Producer(channel, serializer="json").publish(
                payload,
                exchange=DOMAIN_EXCHANGE,
                routing_key=routing_key,
                serializer="json",
                declare=[DOMAIN_EXCHANGE],
                retry=True,
            )


def _publish_job_replay(
    payload: dict[str, object],
    *,
    queue: str,
    routing_key: str,
) -> None:
    from .app import celery_app

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("DEAD_LETTER_JOB_PAYLOAD_INVALID")
    task_name = data.get("task")
    args = data.get("args", [])
    kwargs = data.get("kwargs", {})
    if not isinstance(task_name, str) or not isinstance(args, list) or not isinstance(kwargs, dict):
        raise RuntimeError("DEAD_LETTER_JOB_PAYLOAD_INVALID")
    celery_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        routing_key=routing_key,
    )


def _database_dsn() -> str:
    value = os.getenv("LUMI_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise SystemExit("LUMI_DATABASE_URL/DATABASE_URL is required")
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql://" + value[len("postgresql+asyncpg://") :]
    if value.startswith("postgresql://"):
        return value
    raise SystemExit("DATABASE_URL must use PostgreSQL")


if __name__ == "__main__":
    raise SystemExit(main())
