from __future__ import annotations

from .model import GenerationJob, ImageGenerationSpec
from .ports import PendingInvocationRecord


class GenerationRepositoryError(ValueError):
    pass


class OperationSemanticConflict(GenerationRepositoryError):
    pass


class InMemoryGenerationRepository:
    """Executable async reference repository preserving idempotency and resumability."""

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], GenerationJob] = {}
        self._operations: dict[tuple[str, str], str] = {}
        self._specs: dict[tuple[str, str], ImageGenerationSpec] = {}
        self._pending: dict[tuple[str, str, str], PendingInvocationRecord] = {}

    async def get_by_operation(
        self,
        organization_id: str,
        operation_id: str,
    ) -> GenerationJob | None:
        generation_id = self._operations.get((organization_id, operation_id))
        if generation_id is None:
            return None
        return self._jobs.get((organization_id, generation_id))

    async def get(self, organization_id: str, generation_id: str) -> GenerationJob | None:
        return self._jobs.get((organization_id, generation_id))

    async def save(self, job: GenerationJob) -> None:
        op_key = (job.organization_id, job.operation_id)
        existing_generation_id = self._operations.get(op_key)
        if existing_generation_id is not None:
            existing = self._jobs[(job.organization_id, existing_generation_id)]
            if existing.semantic_hash != job.semantic_hash:
                raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")
            if existing.generation_id != job.generation_id:
                raise GenerationRepositoryError("GENERATION_OPERATION_REBOUND_FORBIDDEN")
        self._operations[op_key] = job.generation_id
        self._jobs[(job.organization_id, job.generation_id)] = job

    async def save_spec(self, spec: ImageGenerationSpec) -> None:
        key = (spec.organization_id, spec.operation_id)
        existing = self._specs.get(key)
        if existing is not None and existing.semantic_hash != spec.semantic_hash:
            raise OperationSemanticConflict("GENERATION_OPERATION_SPEC_CONFLICT")
        self._specs[key] = spec

    async def get_spec(
        self,
        organization_id: str,
        operation_id: str,
    ) -> ImageGenerationSpec | None:
        return self._specs.get((organization_id, operation_id))

    async def save_pending(self, record: PendingInvocationRecord) -> None:
        key = (record.organization_id, record.generation_id, record.candidate_id)
        existing = self._pending.get(key)
        if existing is not None:
            if existing.result.provider_request_id != record.result.provider_request_id:
                raise GenerationRepositoryError("PENDING_INVOCATION_PROVIDER_REQUEST_CHANGED")
            if existing.request.variant_operation_id != record.request.variant_operation_id:
                raise GenerationRepositoryError("PENDING_INVOCATION_OPERATION_CHANGED")
        self._pending[key] = record

    async def get_pending(
        self,
        organization_id: str,
        generation_id: str,
        candidate_id: str,
    ) -> PendingInvocationRecord | None:
        return self._pending.get((organization_id, generation_id, candidate_id))

    async def delete_pending(
        self,
        organization_id: str,
        generation_id: str,
        candidate_id: str,
    ) -> None:
        self._pending.pop((organization_id, generation_id, candidate_id), None)
