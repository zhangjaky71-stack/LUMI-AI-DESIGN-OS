from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from celery import Task
from kombu import Connection, Producer

from .event_runtime import DeadLetterStore
from .queue_contracts import classify_error
from .topology import DEAD_LETTER_EXCHANGE

_TASK_ROUTE: dict[str, tuple[str, str]] = {
    "lumi.jobs.image.transform": ("lumi.media.image", "image.transform"),
    "lumi.jobs.video.render": ("lumi.media.video", "video.render"),
    "lumi.jobs.asset.preview": ("lumi.asset.processing", "asset.processing"),
    "lumi.assets.validate": ("lumi.asset.processing", "asset.processing"),
    "lumi.jobs.export.package": ("lumi.media.export", "export.package"),
}
_FORBIDDEN_KEY_TOKENS = ("secret", "password", "api_key", "access_token")


class RuntimeTask(Task):
    """Records final Celery failures in RabbitMQ DLQ + durable DB evidence."""

    abstract = True

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        try:
            _record_final_failure(self, exc=exc, task_id=task_id, args=args, kwargs=kwargs)
        except Exception:
            # Failure reporting must never mask Celery's original failure state.
            pass
        super().on_failure(exc, task_id, args, kwargs, einfo)


def _record_final_failure(
    task: RuntimeTask,
    *,
    exc: BaseException,
    task_id: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    route = _TASK_ROUTE.get(task.name or "")
    if route is None:
        return
    source_queue, routing_key = route
    first = args[0] if args else None
    raw_payload = first if isinstance(first, dict) else {"job_id": str(first or task_id)}
    message_id = _uuid_text(raw_payload.get("job_id")) or _uuid_text(task_id)
    organization_id = _uuid_text(raw_payload.get("organization_id"))
    trace_id = str(raw_payload.get("trace_id")) if raw_payload.get("trace_id") else None
    retries = int(getattr(task.request, "retries", 0)) + 1
    code = str(getattr(exc, "code", type(exc).__name__))
    category = classify_error(code=code, retryable=getattr(exc, "retryable", None))
    dlq_body = {
        "message_kind": "job",
        "id": message_id or task_id,
        "organizationid": organization_id,
        "traceid": trace_id,
        "task": task.name,
        "celery_task_id": task_id,
        "args": _safe_json(list(args)),
        "kwargs": _safe_json(kwargs),
        "error": {"category": category.value, "code": code, "message": str(exc)[:2000]},
        "attempts": retries,
    }
    dsn = _database_dsn()
    if dsn:
        envelope = {
            "id": message_id or task_id,
            "organizationid": organization_id,
            "traceid": trace_id,
            "data": dlq_body,
        }
        asyncio.run(
            DeadLetterStore(dsn).record(
                envelope=envelope,
                source_queue=source_queue,
                consumer=task.name or "celery",
                exchange_name="lumi.jobs",
                routing_key=routing_key,
                category=category,
                error_code=code,
                error_message=str(exc),
                attempts=retries,
                message_kind="job",
            )
        )
    broker_url = os.getenv("RABBITMQ_URL")
    if broker_url:
        with Connection(broker_url) as connection:
            with connection.channel() as channel:
                Producer(channel, serializer="json").publish(
                    dlq_body,
                    exchange=DEAD_LETTER_EXCHANGE,
                    routing_key=f"{source_queue}.dead",
                    serializer="json",
                    declare=[DEAD_LETTER_EXCHANGE],
                    retry=True,
                )


def _database_dsn() -> str | None:
    value = os.getenv("DATABASE_URL")
    if not value:
        return None
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def _uuid_text(value: Any) -> str | None:
    try:
        return str(UUID(str(value))) if value else None
    except (TypeError, ValueError):
        return None


def _safe_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return "<max-depth>"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if any(token in key_text.lower() for token in _FORBIDDEN_KEY_TOKENS):
                output[key_text] = "<redacted>"
            else:
                output[key_text] = _safe_json(child, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        return [_safe_json(child, depth=depth + 1) for child in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary:{len(value)} bytes>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return f"<{type(value).__name__}>"
