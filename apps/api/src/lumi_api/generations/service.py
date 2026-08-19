from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from lumi_image_generation.model import ImageGenerationSpec
from lumi_image_generation.spec_codec import decode_spec, encode_spec
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.api.v1.contracts import GenerationCreate
from lumi_api.idempotency import canonical_request_hash
from lumi_api.media_dispatch import (
    IMAGE_TASK_INPUT_SCHEMA_VERSION,
    IMAGE_TRANSFORM_JOB_KIND,
    stage_image_transform_dispatch,
)
from lumi_api.persistence.base import utc_now
from lumi_api.persistence.models import Generation, IdempotencyOperation, Project, Task

from .errors import GenerationConflict, GenerationInvalid, GenerationNotFound

_OPERATION_TYPE = "api.v1.generation.create"
_IMAGE_CAPABILITY = "image.generate"
_PROVIDER_PENDING = "model-gateway"
_MODEL_PENDING = "routing-pending"


class ImageGenerationControlPlane:
    """Canonical DB-only producer for hosted image generation.

    The caller owns the surrounding transaction. This service never talks to the
    broker or a model provider. It atomically binds the existing Task, canonical
    Generation snapshot, NODE-20 idempotency operation, and job-dispatch outbox.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        organization_id: UUID,
        payload: GenerationCreate,
        idempotency_key: str,
        trace_id: str | None,
    ) -> Generation:
        spec = self._decode_request(payload)
        request_hash = canonical_request_hash(payload.model_dump(mode="python"))
        await self._lock_idempotency(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        operation = await self._get_idempotency_operation(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if operation is not None:
            if operation.request_hash != request_hash:
                raise GenerationConflict("GENERATION_IDEMPOTENCY_REQUEST_CONFLICT")
            if operation.status == "succeeded":
                return await self._replay_succeeded(
                    organization_id=organization_id,
                    operation=operation,
                )
            raise GenerationConflict(f"GENERATION_IDEMPOTENCY_STATE:{operation.status}")

        task_id = self._required_task_id(payload, spec)
        await self._validate_scope(
            organization_id=organization_id,
            payload=payload,
            spec=spec,
            task_id=task_id,
        )
        existing = await self._generation_by_operation(
            organization_id=organization_id,
            operation_id=UUID(spec.operation_id),
        )
        if existing is not None:
            raise GenerationConflict("GENERATION_OPERATION_ALREADY_EXISTS")

        task = await self._lock_task(
            organization_id=organization_id,
            project_id=payload.project_id,
            task_id=task_id,
        )
        if task is None:
            raise GenerationNotFound("GENERATION_TASK_NOT_FOUND_OR_FORBIDDEN")
        if task.type != IMAGE_TRANSFORM_JOB_KIND:
            raise GenerationInvalid("GENERATION_TASK_TYPE_MISMATCH")
        if task.status not in {"pending", "retrying"}:
            raise GenerationConflict(f"GENERATION_TASK_NOT_DISPATCHABLE:{task.status}")
        if task.agent_run_id != payload.agent_run_id:
            raise GenerationInvalid("GENERATION_TASK_AGENT_RUN_MISMATCH")

        canonical_spec = encode_spec(spec)
        canonical_task_input: dict[str, Any] = {
            "schema_version": IMAGE_TASK_INPUT_SCHEMA_VERSION,
            "job_kind": IMAGE_TRANSFORM_JOB_KIND,
            "image_generation_spec": canonical_spec,
        }
        existing_task_input = dict(task.input_json or {})
        if existing_task_input and existing_task_input != canonical_task_input:
            raise GenerationConflict("GENERATION_TASK_INPUT_CONFLICT")
        task.input_json = canonical_task_input

        operation = IdempotencyOperation(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            operation_type=_OPERATION_TYPE,
            business_scope_id=task_id,
            status="in_progress",
            request_hash=request_hash,
            attempt_count=1,
        )
        self.session.add(operation)

        generation = Generation(
            organization_id=organization_id,
            project_id=payload.project_id,
            task_id=task_id,
            agent_run_id=payload.agent_run_id,
            operation_id=UUID(spec.operation_id),
            provider=_PROVIDER_PENDING,
            model=_MODEL_PENDING,
            capability=_IMAGE_CAPABILITY,
            status="pending",
            request_json=canonical_spec,
            result_json={},
        )
        self.session.add(generation)
        await self.session.flush()

        stage_image_transform_dispatch(
            self.session,
            task=task,
            generation=generation,
            trace_id=trace_id,
        )
        await self.session.flush()

        operation.status = "succeeded"
        operation.result_ref = f"generation:{generation.id}"
        operation.result_json = {"generation_id": str(generation.id)}
        operation.response_status = 202
        operation.completed_at = utc_now()
        await self.session.flush()
        return generation

    async def get(self, *, organization_id: UUID, generation_id: UUID) -> Generation:
        result = await self.session.execute(
            select(Generation).where(
                Generation.id == generation_id,
                Generation.organization_id == organization_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise GenerationNotFound("GENERATION_NOT_FOUND_OR_FORBIDDEN")
        return row

    @staticmethod
    def _decode_request(payload: GenerationCreate) -> ImageGenerationSpec:
        if payload.capability != _IMAGE_CAPABILITY:
            raise GenerationInvalid("GENERATION_CAPABILITY_UNSUPPORTED")
        if payload.provider not in {None, _PROVIDER_PENDING}:
            raise GenerationInvalid("GENERATION_PROVIDER_OVERRIDE_FORBIDDEN")
        if payload.model not in {None, _MODEL_PENDING}:
            raise GenerationInvalid("GENERATION_MODEL_OVERRIDE_FORBIDDEN")
        if not isinstance(payload.request, dict):
            raise GenerationInvalid("GENERATION_SPEC_OBJECT_REQUIRED")
        try:
            return decode_spec(payload.request)
        except (TypeError, ValueError) as exc:
            raise GenerationInvalid(f"GENERATION_SPEC_INVALID:{exc}") from exc

    @staticmethod
    def _required_task_id(payload: GenerationCreate, spec: ImageGenerationSpec) -> UUID:
        if payload.task_id is None:
            raise GenerationInvalid("GENERATION_TASK_ID_REQUIRED")
        try:
            spec_task_id = UUID(spec.task_id)
        except ValueError as exc:
            raise GenerationInvalid("GENERATION_SPEC_TASK_ID_INVALID") from exc
        if spec_task_id != payload.task_id:
            raise GenerationInvalid("GENERATION_SPEC_TASK_MISMATCH")
        return payload.task_id

    async def _validate_scope(
        self,
        *,
        organization_id: UUID,
        payload: GenerationCreate,
        spec: ImageGenerationSpec,
        task_id: UUID,
    ) -> None:
        try:
            spec_organization_id = UUID(spec.organization_id)
            spec_project_id = UUID(spec.project_id)
            spec_operation_id = UUID(spec.operation_id)
            spec_agent_run_id = UUID(spec.agent_run_id) if spec.agent_run_id else None
        except ValueError as exc:
            raise GenerationInvalid("GENERATION_SPEC_SCOPE_INVALID") from exc
        if spec_organization_id != organization_id:
            raise GenerationNotFound("GENERATION_PROJECT_NOT_FOUND_OR_FORBIDDEN")
        if spec_project_id != payload.project_id:
            raise GenerationInvalid("GENERATION_SPEC_PROJECT_MISMATCH")
        if spec_agent_run_id != payload.agent_run_id:
            raise GenerationInvalid("GENERATION_SPEC_AGENT_RUN_MISMATCH")
        if not spec_operation_id:
            raise GenerationInvalid("GENERATION_OPERATION_ID_REQUIRED")
        if UUID(spec.task_id) != task_id:
            raise GenerationInvalid("GENERATION_SPEC_TASK_MISMATCH")

        project = await self.session.scalar(
            select(Project).where(
                Project.id == payload.project_id,
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
        )
        if project is None or project.status == "archived":
            raise GenerationNotFound("GENERATION_PROJECT_NOT_FOUND_OR_FORBIDDEN")

    async def _lock_task(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        task_id: UUID,
    ) -> Task | None:
        result = await self.session.execute(
            select(Task)
            .where(
                Task.id == task_id,
                Task.organization_id == organization_id,
                Task.project_id == project_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _generation_by_operation(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
    ) -> Generation | None:
        result = await self.session.execute(
            select(Generation)
            .where(
                Generation.organization_id == organization_id,
                Generation.operation_id == operation_id,
            )
            .order_by(Generation.created_at, Generation.id)
            .limit(2)
            .with_for_update()
        )
        rows = result.scalars().all()
        if len(rows) > 1:
            raise GenerationConflict("GENERATION_OPERATION_DUPLICATE")
        return rows[0] if rows else None

    async def _lock_idempotency(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _lock_key(organization_id, idempotency_key)},
        )

    async def _get_idempotency_operation(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> IdempotencyOperation | None:
        result = await self.session.execute(
            select(IdempotencyOperation)
            .where(
                IdempotencyOperation.organization_id == organization_id,
                IdempotencyOperation.operation_type == _OPERATION_TYPE,
                IdempotencyOperation.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _replay_succeeded(
        self,
        *,
        organization_id: UUID,
        operation: IdempotencyOperation,
    ) -> Generation:
        raw_id = dict(operation.result_json or {}).get("generation_id")
        if not isinstance(raw_id, str):
            raise GenerationConflict("GENERATION_IDEMPOTENCY_RESULT_MISSING")
        try:
            generation_id = UUID(raw_id)
        except ValueError as exc:
            raise GenerationConflict("GENERATION_IDEMPOTENCY_RESULT_INVALID") from exc
        result = await self.session.execute(
            select(Generation).where(
                Generation.id == generation_id,
                Generation.organization_id == organization_id,
            )
        )
        generation = result.scalar_one_or_none()
        if generation is None:
            raise GenerationConflict("GENERATION_IDEMPOTENCY_RESULT_DANGLING")
        return generation


def _lock_key(organization_id: UUID, idempotency_key: str) -> int:
    digest = hashlib.sha256(
        f"{_OPERATION_TYPE}\x00{organization_id}\x00{idempotency_key}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)
