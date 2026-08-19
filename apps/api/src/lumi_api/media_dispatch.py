from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from lumi_domain.job_dispatch import JobMessage, validate_job_payload
from lumi_image_generation.spec_codec import decode_spec
from sqlalchemy.ext.asyncio import AsyncSession

from .persistence.models import Generation, OutboxEvent, Task

IMAGE_TRANSFORM_JOB_KIND = "image.transform"
IMAGE_TRANSFORM_TASK_NAME = "lumi.jobs.image.transform"
IMAGE_TRANSFORM_QUEUE = "lumi.media.image"
IMAGE_TASK_INPUT_SCHEMA_VERSION = 1
MEDIA_DISPATCH_EVENT_NAME = "job.dispatch.requested"
MEDIA_DISPATCH_SCHEMA_VERSION = 1


class MediaTaskBroker(Protocol):
    """Infrastructure port implemented by the outbox publisher process, never HTTP routes."""

    async def publish_task(
        self,
        *,
        task_name: str,
        queue: str,
        args: list[object],
        kwargs: dict[str, object],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CanonicalMediaDispatch:
    task_name: str
    queue: str
    message: JobMessage

    def as_outbox_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "task_name": self.task_name,
            "queue": self.queue,
            "args": [self.message.as_dict()],
            "kwargs": {},
        }
        validate_job_payload(payload)
        return payload

    @classmethod
    def from_outbox_payload(cls, value: object) -> CanonicalMediaDispatch:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ValueError("MEDIA_DISPATCH_PAYLOAD_OBJECT_REQUIRED")
        allowed = {"task_name", "queue", "args", "kwargs"}
        unknown = set(value) - allowed
        missing = allowed - set(value)
        if unknown:
            raise ValueError(f"MEDIA_DISPATCH_UNKNOWN_FIELDS:{','.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"MEDIA_DISPATCH_REQUIRED:{','.join(sorted(missing))}")
        if value["task_name"] != IMAGE_TRANSFORM_TASK_NAME:
            raise ValueError("MEDIA_DISPATCH_TASK_NAME_MISMATCH")
        if value["queue"] != IMAGE_TRANSFORM_QUEUE:
            raise ValueError("MEDIA_DISPATCH_QUEUE_MISMATCH")
        args = value["args"]
        if not isinstance(args, list) or len(args) != 1 or not isinstance(args[0], dict):
            raise ValueError("MEDIA_DISPATCH_ARGS_INVALID")
        kwargs = value["kwargs"]
        if not isinstance(kwargs, dict) or kwargs:
            raise ValueError("MEDIA_DISPATCH_KWARGS_FORBIDDEN")
        validate_job_payload(value)
        return cls(
            task_name=IMAGE_TRANSFORM_TASK_NAME,
            queue=IMAGE_TRANSFORM_QUEUE,
            message=JobMessage.from_mapping(args[0]),
        )


def build_image_transform_dispatch(
    *,
    task: Task,
    generation: Generation,
    trace_id: str | None,
) -> CanonicalMediaDispatch:
    task_id = _uuid(task.id, "MEDIA_DISPATCH_TASK_ID_REQUIRED")
    organization_id = _uuid(task.organization_id, "MEDIA_DISPATCH_ORGANIZATION_ID_REQUIRED")
    project_id = _uuid(task.project_id, "MEDIA_DISPATCH_PROJECT_ID_REQUIRED")
    if task.type != IMAGE_TRANSFORM_JOB_KIND:
        raise ValueError("MEDIA_DISPATCH_TASK_TYPE_MISMATCH")
    if generation.task_id != task_id:
        raise ValueError("MEDIA_DISPATCH_GENERATION_TASK_MISMATCH")
    if generation.organization_id != organization_id:
        raise ValueError("MEDIA_DISPATCH_GENERATION_ORGANIZATION_MISMATCH")
    if generation.project_id != project_id:
        raise ValueError("MEDIA_DISPATCH_GENERATION_PROJECT_MISMATCH")
    operation_id = _uuid(
        generation.operation_id,
        "MEDIA_DISPATCH_GENERATION_OPERATION_REQUIRED",
    )

    task_input = _object(task.input_json, "MEDIA_DISPATCH_TASK_INPUT_INVALID")
    expected_task_input_fields = {"schema_version", "job_kind", "image_generation_spec"}
    if set(task_input) != expected_task_input_fields:
        raise ValueError("MEDIA_DISPATCH_TASK_INPUT_FIELDS_INVALID")
    if task_input.get("schema_version") != IMAGE_TASK_INPUT_SCHEMA_VERSION:
        raise ValueError("MEDIA_DISPATCH_TASK_INPUT_SCHEMA_UNSUPPORTED")
    if task_input.get("job_kind") != IMAGE_TRANSFORM_JOB_KIND:
        raise ValueError("MEDIA_DISPATCH_TASK_INPUT_KIND_MISMATCH")
    raw_spec = _object(
        task_input.get("image_generation_spec"),
        "MEDIA_DISPATCH_TASK_SPEC_MISSING",
    )
    task_spec = decode_spec(raw_spec)
    generation_spec = decode_spec(
        _object(generation.request_json, "MEDIA_DISPATCH_GENERATION_SPEC_MISSING")
    )
    if task_spec.semantic_hash != generation_spec.semantic_hash:
        raise ValueError("MEDIA_DISPATCH_GENERATION_SPEC_MISMATCH")
    if UUID(task_spec.organization_id) != organization_id:
        raise ValueError("MEDIA_DISPATCH_SPEC_ORGANIZATION_MISMATCH")
    if UUID(task_spec.project_id) != project_id:
        raise ValueError("MEDIA_DISPATCH_SPEC_PROJECT_MISMATCH")
    if UUID(task_spec.task_id) != task_id:
        raise ValueError("MEDIA_DISPATCH_SPEC_TASK_MISMATCH")
    if UUID(task_spec.operation_id) != operation_id:
        raise ValueError("MEDIA_DISPATCH_SPEC_OPERATION_MISMATCH")

    message = JobMessage(
        job_id=task_id,
        organization_id=organization_id,
        project_id=project_id,
        operation_id=operation_id,
        trace_id=trace_id,
    )
    dispatch = CanonicalMediaDispatch(
        task_name=IMAGE_TRANSFORM_TASK_NAME,
        queue=IMAGE_TRANSFORM_QUEUE,
        message=message,
    )
    dispatch.as_outbox_payload()
    return dispatch


def stage_image_transform_dispatch(
    session: AsyncSession,
    *,
    task: Task,
    generation: Generation,
    trace_id: str | None,
) -> OutboxEvent:
    """Stage a dispatch in the caller's DB transaction; this function never touches the broker."""

    dispatch = build_image_transform_dispatch(
        task=task,
        generation=generation,
        trace_id=trace_id,
    )
    event = OutboxEvent(
        organization_id=dispatch.message.organization_id,
        event_name=MEDIA_DISPATCH_EVENT_NAME,
        aggregate_type="task",
        aggregate_id=dispatch.message.job_id,
        schema_version=MEDIA_DISPATCH_SCHEMA_VERSION,
        payload_json=dispatch.as_outbox_payload(),
        publish_attempts=0,
    )
    session.add(event)
    return event


async def publish_media_outbox_event(
    *,
    event: OutboxEvent,
    broker: MediaTaskBroker,
    published_at: datetime | None = None,
) -> bool:
    """Publish one staged event and update its in-session delivery state.

    The caller owns the transaction that persists publish_attempts/published_at.
    On broker failure publish_attempts is still incremented in memory and
    published_at remains unset so the caller can durably record the failed
    attempt before retry scheduling.
    """

    if event.published_at is not None:
        return False
    if event.event_name != MEDIA_DISPATCH_EVENT_NAME:
        raise ValueError("MEDIA_DISPATCH_EVENT_NAME_MISMATCH")
    if event.aggregate_type != "task":
        raise ValueError("MEDIA_DISPATCH_AGGREGATE_TYPE_MISMATCH")
    if event.schema_version != MEDIA_DISPATCH_SCHEMA_VERSION:
        raise ValueError("MEDIA_DISPATCH_EVENT_SCHEMA_UNSUPPORTED")
    dispatch = CanonicalMediaDispatch.from_outbox_payload(event.payload_json)
    if dispatch.message.job_id != event.aggregate_id:
        raise ValueError("MEDIA_DISPATCH_AGGREGATE_ID_MISMATCH")
    if dispatch.message.organization_id != event.organization_id:
        raise ValueError("MEDIA_DISPATCH_EVENT_ORGANIZATION_MISMATCH")

    event.publish_attempts += 1
    await broker.publish_task(
        task_name=dispatch.task_name,
        queue=dispatch.queue,
        args=[dispatch.message.as_dict()],
        kwargs={},
    )
    event.published_at = published_at or datetime.now(UTC)
    return True


def _object(value: object, error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(error)
    return value


def _uuid(value: object, error: str) -> UUID:
    if not isinstance(value, UUID):
        raise ValueError(error)
    return value
