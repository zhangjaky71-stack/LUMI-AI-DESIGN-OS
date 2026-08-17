from __future__ import annotations

from .model import VideoJob


class VideoOperationConflict(RuntimeError):
    pass


class InMemoryVideoRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._operation_index: dict[tuple[str, str], str] = {}
        self._webhooks: set[tuple[str, str, str]] = set()

    def create(self, job: VideoJob) -> VideoJob:
        operation_key = (job.spec.organization_id, job.spec.operation_id)
        existing_id = self._operation_index.get(operation_key)
        if existing_id is not None:
            existing = self._jobs[existing_id]
            if existing.spec.semantic_hash() != job.spec.semantic_hash():
                raise VideoOperationConflict(
                    "VIDEO_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing
        if job.job_id in self._jobs:
            raise VideoOperationConflict("VIDEO_JOB_ID_ALREADY_EXISTS")
        self._jobs[job.job_id] = job
        self._operation_index[operation_key] = job.job_id
        return job

    def get(self, job_id: str) -> VideoJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError("VIDEO_JOB_NOT_FOUND") from exc

    def save(self, job: VideoJob) -> VideoJob:
        if job.job_id not in self._jobs:
            raise KeyError("VIDEO_JOB_NOT_FOUND")
        self._jobs[job.job_id] = job
        return job

    def claim_webhook(
        self,
        organization_id: str,
        provider: str,
        event_id: str,
    ) -> bool:
        key = (organization_id, provider, event_id)
        if key in self._webhooks:
            return False
        self._webhooks.add(key)
        return True
