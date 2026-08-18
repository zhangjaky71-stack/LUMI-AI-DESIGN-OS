from __future__ import annotations

from .engine import AutoRepairOperationConflict
from .model import AutoRepairJob


class InMemoryAutoRepairRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, AutoRepairJob] = {}
        self._operations: dict[tuple[str, str], str] = {}

    def create(self, job: AutoRepairJob) -> AutoRepairJob:
        key = (job.spec.organization_id, job.spec.operation_id)
        existing_id = self._operations.get(key)
        if existing_id is not None:
            existing = self._jobs[existing_id]
            if existing.spec.semantic_hash() != job.spec.semantic_hash():
                raise AutoRepairOperationConflict(
                    "REPAIR_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing
        if job.job_id in self._jobs:
            raise AutoRepairOperationConflict("REPAIR_JOB_ID_ALREADY_EXISTS")
        self._jobs[job.job_id] = job
        self._operations[key] = job.job_id
        return job

    def get(self, job_id: str) -> AutoRepairJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError("REPAIR_JOB_NOT_FOUND") from exc

    def save(self, job: AutoRepairJob) -> AutoRepairJob:
        if job.job_id not in self._jobs:
            raise KeyError("REPAIR_JOB_NOT_FOUND")
        self._jobs[job.job_id] = job
        return job

    def get_by_operation(
        self,
        *,
        organization_id: str,
        operation_id: str,
    ) -> AutoRepairJob | None:
        job_id = self._operations.get((organization_id, operation_id))
        return None if job_id is None else self._jobs[job_id]
