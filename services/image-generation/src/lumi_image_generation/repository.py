from __future__ import annotations

from .model import GenerationJob


class GenerationRepositoryError(ValueError):
    pass


class OperationSemanticConflict(GenerationRepositoryError):
    pass


class InMemoryGenerationRepository:
    """Executable reference repository preserving NODE-20-style operation idempotency."""

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], GenerationJob] = {}
        self._operations: dict[tuple[str, str], str] = {}

    def get_by_operation(self, organization_id: str, operation_id: str) -> GenerationJob | None:
        generation_id = self._operations.get((organization_id, operation_id))
        if generation_id is None:
            return None
        return self._jobs.get((organization_id, generation_id))

    def get(self, organization_id: str, generation_id: str) -> GenerationJob | None:
        return self._jobs.get((organization_id, generation_id))

    def save(self, job: GenerationJob) -> None:
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
