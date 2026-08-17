from __future__ import annotations

from threading import RLock
from uuid import UUID

from .model import GenerationJob, ImageGenerationSpec
from .ports import PendingInvocation


class OperationSemanticConflict(ValueError):
    pass


class InMemoryGenerationRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self.jobs: dict[tuple[UUID, UUID], GenerationJob] = {}
        self.jobs_by_id: dict[tuple[UUID, UUID], GenerationJob] = {}
        self.specs: dict[tuple[UUID, UUID], ImageGenerationSpec] = {}
        self.pending: dict[tuple[UUID, UUID, UUID], PendingInvocation] = {}

    def get_by_operation(
        self, organization_id: UUID, operation_id: UUID
    ) -> GenerationJob | None:
        with self._lock:
            return self.jobs.get((organization_id, operation_id))

    def save_spec(self, spec: ImageGenerationSpec) -> None:
        key = (spec.organization_id, spec.operation_id)
        with self._lock:
            existing = self.specs.get(key)
            if existing is not None and existing.semantic_hash != spec.semantic_hash:
                raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")
            self.specs[key] = spec

    def get_spec(
        self, organization_id: UUID, operation_id: UUID
    ) -> ImageGenerationSpec | None:
        with self._lock:
            return self.specs.get((organization_id, operation_id))

    def save(self, job: GenerationJob) -> None:
        operation_key = (job.organization_id, job.operation_id)
        id_key = (job.organization_id, job.generation_id)
        with self._lock:
            existing = self.jobs.get(operation_key)
            if existing is not None and existing.semantic_hash != job.semantic_hash:
                raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")
            self.jobs[operation_key] = job
            self.jobs_by_id[id_key] = job

    def get(self, organization_id: UUID, generation_id: UUID) -> GenerationJob | None:
        with self._lock:
            return self.jobs_by_id.get((organization_id, generation_id))

    def save_pending(self, value: PendingInvocation) -> None:
        key = (value.organization_id, value.generation_id, value.candidate_id)
        with self._lock:
            self.pending[key] = value

    def get_pending(
        self, organization_id: UUID, generation_id: UUID, candidate_id: UUID
    ) -> PendingInvocation | None:
        with self._lock:
            return self.pending.get((organization_id, generation_id, candidate_id))

    def delete_pending(
        self, organization_id: UUID, generation_id: UUID, candidate_id: UUID
    ) -> None:
        with self._lock:
            self.pending.pop((organization_id, generation_id, candidate_id), None)
