from __future__ import annotations

from .model import ProviderJobRecord, VideoJob, VideoTaskSpec


class VideoOperationConflict(ValueError):
    pass


class InMemoryVideoRepository:
    def __init__(self) -> None:
        self.jobs: dict[tuple[str, str], VideoJob] = {}
        self.jobs_by_id: dict[tuple[str, str], VideoJob] = {}
        self.specs: dict[tuple[str, str], VideoTaskSpec] = {}
        self.provider_jobs: dict[tuple[str, str, str], ProviderJobRecord] = {}
        self.terminal_provider_jobs: dict[tuple[str, str, str, str], ProviderJobRecord] = {}

    def get_by_operation(self, organization_id: str, operation_id: str) -> VideoJob | None:
        return self.jobs.get((organization_id, operation_id))

    def get(self, organization_id: str, video_job_id: str) -> VideoJob | None:
        return self.jobs_by_id.get((organization_id, video_job_id))

    def save_spec(self, spec: VideoTaskSpec) -> None:
        key = (spec.organization_id, spec.operation_id)
        existing = self.specs.get(key)
        if existing is not None and existing.semantic_hash != spec.semantic_hash:
            raise VideoOperationConflict("VIDEO_OPERATION_SEMANTIC_CONFLICT")
        self.specs[key] = spec

    def get_spec(self, organization_id: str, operation_id: str) -> VideoTaskSpec | None:
        return self.specs.get((organization_id, operation_id))

    def save(self, job: VideoJob) -> None:
        key = (job.organization_id, job.operation_id)
        existing = self.jobs.get(key)
        if existing is not None and existing.semantic_hash != job.semantic_hash:
            raise VideoOperationConflict("VIDEO_OPERATION_SEMANTIC_CONFLICT")
        self.jobs[key] = job
        self.jobs_by_id[(job.organization_id, job.video_job_id)] = job

    def save_provider_job(self, record: ProviderJobRecord) -> None:
        active_key = (record.organization_id, record.video_job_id, record.shot_id)
        terminal_key = active_key + (record.paid_operation_id,)
        active = self.provider_jobs.get(active_key)
        terminal = self.terminal_provider_jobs.get(terminal_key)
        existing = active or terminal
        if existing is not None and (
            existing.paid_operation_id != record.paid_operation_id
            or existing.request_hash != record.request_hash
            or existing.result.provider_request_id != record.result.provider_request_id
        ):
            raise VideoOperationConflict("VIDEO_PROVIDER_JOB_IDENTITY_CONFLICT")
        if active is not None and active.paid_operation_id != record.paid_operation_id:
            raise VideoOperationConflict("VIDEO_PROVIDER_ACTIVE_ATTEMPT_CONFLICT")
        self.provider_jobs[active_key] = record
        self.terminal_provider_jobs.pop(terminal_key, None)

    def get_provider_job(
        self,
        organization_id: str,
        video_job_id: str,
        shot_id: str,
        paid_operation_id: str,
    ) -> ProviderJobRecord | None:
        active_key = (organization_id, video_job_id, shot_id)
        active = self.provider_jobs.get(active_key)
        if active is not None:
            return active if active.paid_operation_id == paid_operation_id else None
        return self.terminal_provider_jobs.get(active_key + (paid_operation_id,))

    def delete_provider_job(
        self,
        organization_id: str,
        video_job_id: str,
        shot_id: str,
        paid_operation_id: str,
    ) -> None:
        """Archive provider identity by paid attempt so retries remain independently replayable."""
        active_key = (organization_id, video_job_id, shot_id)
        record = self.provider_jobs.get(active_key)
        if record is None:
            return
        if record.paid_operation_id != paid_operation_id:
            raise VideoOperationConflict("VIDEO_PROVIDER_ARCHIVE_ATTEMPT_MISMATCH")
        self.provider_jobs.pop(active_key, None)
        self.terminal_provider_jobs[active_key + (paid_operation_id,)] = record
