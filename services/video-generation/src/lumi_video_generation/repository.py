from __future__ import annotations

from dataclasses import replace

from .model import ProviderJobRecord, VideoJob, VideoTaskSpec


class VideoOperationConflict(ValueError):
    pass


class InMemoryVideoRepository:
    def __init__(self) -> None:
        self.jobs: dict[tuple[str, str], VideoJob] = {}
        self.jobs_by_id: dict[tuple[str, str], VideoJob] = {}
        self.specs: dict[tuple[str, str], VideoTaskSpec] = {}
        self.provider_jobs: dict[tuple[str, str, str], ProviderJobRecord] = {}

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
        key = (record.organization_id, record.video_job_id, record.shot_id)
        existing = self.provider_jobs.get(key)
        if existing is not None and (
            existing.paid_operation_id != record.paid_operation_id
            or existing.request_hash != record.request_hash
            or existing.result.provider_request_id != record.result.provider_request_id
        ):
            raise VideoOperationConflict("VIDEO_PROVIDER_JOB_IDENTITY_CONFLICT")
        self.provider_jobs[key] = record

    def get_provider_job(self, organization_id: str, video_job_id: str, shot_id: str) -> ProviderJobRecord | None:
        return self.provider_jobs.get((organization_id, video_job_id, shot_id))

    def delete_provider_job(self, organization_id: str, video_job_id: str, shot_id: str) -> None:
        self.provider_jobs.pop((organization_id, video_job_id, shot_id), None)

    def update_job_costs(self, job: VideoJob, *, estimated_delta: object = None, actual_delta: object = None) -> VideoJob:
        del estimated_delta, actual_delta
        return replace(job)
