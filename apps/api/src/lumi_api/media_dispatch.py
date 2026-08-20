from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

from lumi_domain.job_dispatch import (
    IMAGE_TRANSFORM_JOB_KIND,
    IMAGE_TRANSFORM_QUEUE,
    IMAGE_TRANSFORM_TASK_NAME,
    JOB_DISPATCH_EVENT_NAME,
    JOB_DISPATCH_SCHEMA_VERSION,
    VIDEO_RENDER_JOB_KIND,
    VIDEO_RENDER_QUEUE,
    VIDEO_RENDER_TASK_NAME,
    JobDispatch,
    JobMessage,
)
from lumi_image_generation.spec_codec import decode_spec as decode_image_spec
from lumi_video_generation.spec_codec import decode_spec as decode_video_spec
from sqlalchemy.ext.asyncio import AsyncSession

from .persistence.models import Generation, OutboxEvent, Task

IMAGE_TASK_INPUT_SCHEMA_VERSION = 1
VIDEO_TASK_INPUT_SCHEMA_VERSION = 1
MEDIA_DISPATCH_EVENT_NAME = JOB_DISPATCH_EVENT_NAME
MEDIA_DISPATCH_SCHEMA_VERSION = JOB_DISPATCH_SCHEMA_VERSION
CanonicalMediaDispatch = JobDispatch


def build_image_transform_dispatch(
    *,
    task: Task,
    generation: Generation,
    trace_id: str | None,
) -> JobDispatch:
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
    task_spec = decode_image_spec(raw_spec)
    generation_spec = decode_image_spec(
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

    dispatch = JobDispatch(
        task_name=IMAGE_TRANSFORM_TASK_NAME,
        queue=IMAGE_TRANSFORM_QUEUE,
        message=JobMessage(
            job_id=task_id,
            organization_id=organization_id,
            project_id=project_id,
            operation_id=operation_id,
            trace_id=trace_id,
        ),
    )
    dispatch.as_outbox_payload()
    return dispatch


def build_video_render_dispatch(
    *,
    task: Task,
    trace_id: str | None,
) -> JobDispatch:
    task_id = _uuid(task.id, "VIDEO_DISPATCH_TASK_ID_REQUIRED")
    organization_id = _uuid(task.organization_id, "VIDEO_DISPATCH_ORGANIZATION_ID_REQUIRED")
    project_id = _uuid(task.project_id, "VIDEO_DISPATCH_PROJECT_ID_REQUIRED")
    if task.type != VIDEO_RENDER_JOB_KIND:
        raise ValueError("VIDEO_DISPATCH_TASK_TYPE_MISMATCH")

    task_input = _object(task.input_json, "VIDEO_DISPATCH_TASK_INPUT_INVALID")
    expected_fields = {"schema_version", "job_kind", "video_generation_spec"}
    if set(task_input) != expected_fields:
        raise ValueError("VIDEO_DISPATCH_TASK_INPUT_FIELDS_INVALID")
    if task_input.get("schema_version") != VIDEO_TASK_INPUT_SCHEMA_VERSION:
        raise ValueError("VIDEO_DISPATCH_TASK_INPUT_SCHEMA_UNSUPPORTED")
    if task_input.get("job_kind") != VIDEO_RENDER_JOB_KIND:
        raise ValueError("VIDEO_DISPATCH_TASK_INPUT_KIND_MISMATCH")
    spec = decode_video_spec(
        _object(task_input.get("video_generation_spec"), "VIDEO_DISPATCH_TASK_SPEC_MISSING")
    )
    if UUID(spec.organization_id) != organization_id:
        raise ValueError("VIDEO_DISPATCH_SPEC_ORGANIZATION_MISMATCH")
    if UUID(spec.project_id) != project_id:
        raise ValueError("VIDEO_DISPATCH_SPEC_PROJECT_MISMATCH")
    if UUID(spec.task_id) != task_id:
        raise ValueError("VIDEO_DISPATCH_SPEC_TASK_MISMATCH")
    operation_id = UUID(spec.operation_id)

    dispatch = JobDispatch(
        task_name=VIDEO_RENDER_TASK_NAME,
        queue=VIDEO_RENDER_QUEUE,
        message=JobMessage(
            job_id=task_id,
            organization_id=organization_id,
            project_id=project_id,
            operation_id=operation_id,
            trace_id=trace_id,
        ),
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
    """Stage the canonical image dispatch in the caller's transaction."""

    return _stage_dispatch(
        session,
        dispatch=build_image_transform_dispatch(
            task=task,
            generation=generation,
            trace_id=trace_id,
        ),
        namespace="image-transform",
    )


def stage_video_render_dispatch(
    session: AsyncSession,
    *,
    task: Task,
    trace_id: str | None,
) -> OutboxEvent:
    """Stage the canonical video dispatch in the caller's transaction."""

    return _stage_dispatch(
        session,
        dispatch=build_video_render_dispatch(task=task, trace_id=trace_id),
        namespace="video-render",
    )


def _stage_dispatch(
    session: AsyncSession,
    *,
    dispatch: JobDispatch,
    namespace: str,
) -> OutboxEvent:
    operation_id = dispatch.message.operation_id
    if operation_id is None:
        raise ValueError("MEDIA_DISPATCH_OPERATION_REQUIRED")
    event = OutboxEvent(
        id=_dispatch_event_id(operation_id, dispatch.message.job_id, namespace=namespace),
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


def _dispatch_event_id(operation_id: UUID, task_id: UUID, *, namespace: str) -> UUID:
    if namespace not in {"image-transform", "video-render"}:
        raise ValueError("MEDIA_DISPATCH_NAMESPACE_INVALID")
    return uuid5(operation_id, f"lumi:{namespace}-dispatch:{task_id}")


def _object(value: object, error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(error)
    return value


def _uuid(value: object, error: str) -> UUID:
    if not isinstance(value, UUID):
        raise ValueError(error)
    return value
