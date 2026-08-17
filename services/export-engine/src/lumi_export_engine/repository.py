from __future__ import annotations

from .model import DownloadGrant, ExportJob
from .pipeline import ExportOperationConflict


class InMemoryExportRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, ExportJob] = {}
        self._operation_index: dict[tuple[str, str], str] = {}
        self._grants: dict[str, tuple[str, str, str]] = {}

    def create(self, job: ExportJob) -> ExportJob:
        key = (job.spec.organization_id, job.spec.operation_id)
        existing_id = self._operation_index.get(key)
        if existing_id is not None:
            existing = self._jobs[existing_id]
            if existing.spec.semantic_hash() != job.spec.semantic_hash():
                raise ExportOperationConflict(
                    "EXPORT_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing
        if job.job_id in self._jobs:
            raise ExportOperationConflict("EXPORT_JOB_ID_ALREADY_EXISTS")
        self._jobs[job.job_id] = job
        self._operation_index[key] = job.job_id
        return job

    def get(self, job_id: str) -> ExportJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError("EXPORT_JOB_NOT_FOUND") from exc

    def save(self, job: ExportJob) -> ExportJob:
        if job.job_id not in self._jobs:
            raise KeyError("EXPORT_JOB_NOT_FOUND")
        self._jobs[job.job_id] = job
        return job

    def record_grant(self, grant: DownloadGrant) -> None:
        existing = self._grants.get(grant.grant_id)
        value = (grant.package_id, grant.actor_id, grant.expires_at.isoformat())
        if existing is not None and existing != value:
            raise ValueError("EXPORT_GRANT_ID_REUSED_WITH_DIFFERENT_METADATA")
        self._grants[grant.grant_id] = value
