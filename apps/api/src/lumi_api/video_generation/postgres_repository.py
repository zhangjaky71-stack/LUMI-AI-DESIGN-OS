from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lumi_video_generation import ShotStatus, VideoJob
from lumi_video_generation.repository import VideoOperationConflict
from lumi_api.persistence.models_video_generation import (
    VideoGenerationClipModel,
    VideoGenerationCostProjectionModel,
    VideoGenerationJobModel,
    VideoGenerationShotModel,
    VideoGenerationSpecModel,
    VideoProviderJobModel,
    VideoWebhookDedupeModel,
)

from .codec import encode_job, encode_spec


class PostgresVideoRepository:
    """Durable NODE-48 repository used by queue/webhook workers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, job: VideoJob) -> VideoJob:
        job_id = UUID(job.job_id)
        organization_id = UUID(job.spec.organization_id)
        operation_id = UUID(job.spec.operation_id)
        prior = self.session.scalar(
            select(VideoGenerationSpecModel).where(
                VideoGenerationSpecModel.organization_id == organization_id,
                VideoGenerationSpecModel.operation_id == operation_id,
            )
        )
        if prior is not None:
            if prior.semantic_hash != job.spec.semantic_hash():
                raise VideoOperationConflict(
                    "VIDEO_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            existing = self.session.get(VideoGenerationJobModel, prior.video_job_id)
            if existing is None:
                raise RuntimeError("VIDEO_OPERATION_BOUND_WITHOUT_JOB")
            from .codec import decode_job

            return decode_job(dict(existing.job_json))

        spec_row = VideoGenerationSpecModel(
            video_job_id=job_id,
            organization_id=organization_id,
            project_id=UUID(job.spec.project_id),
            task_id=UUID(job.spec.task_id),
            operation_id=operation_id,
            semantic_hash=job.spec.semantic_hash(),
            mode=job.spec.mode.value,
            width=job.spec.width,
            height=job.spec.height,
            fps=job.spec.fps,
            budget_limit_usd=job.spec.budget_limit_usd,
            spec_json=encode_spec(job.spec),
        )
        self.session.add(spec_row)
        self.session.flush()
        self._write_job(job)
        self.session.commit()
        return job

    def get(self, job_id: str) -> VideoJob:
        row = self.session.get(VideoGenerationJobModel, UUID(job_id))
        if row is None:
            raise KeyError("VIDEO_JOB_NOT_FOUND")
        from .codec import decode_job

        return decode_job(dict(row.job_json))

    def save(self, job: VideoJob) -> VideoJob:
        spec = self.session.get(VideoGenerationSpecModel, UUID(job.job_id))
        if spec is None:
            raise KeyError("VIDEO_JOB_NOT_FOUND")
        if (
            spec.organization_id != UUID(job.spec.organization_id)
            or spec.semantic_hash != job.spec.semantic_hash()
        ):
            raise VideoOperationConflict("VIDEO_JOB_SPEC_CONFLICT")
        self._write_job(job)
        self.session.commit()
        return job

    def _write_job(self, job: VideoJob) -> None:
        job_id = UUID(job.job_id)
        organization_id = UUID(job.spec.organization_id)
        row = self.session.get(VideoGenerationJobModel, job_id)
        values = {
            "organization_id": organization_id,
            "status": job.status.value,
            "final_artifact_version_id": (
                UUID(job.final_artifact_version_id)
                if job.final_artifact_version_id
                else None
            ),
            "final_durable_ref": (
                job.final_video.durable_ref if job.final_video else None
            ),
            "provenance_json": (
                encode_job(job).get("provenance")
                if job.provenance is not None
                else None
            ),
            "job_json": encode_job(job),
            "error_code": job.error_code,
            "updated_at": datetime.now(UTC),
        }
        if row is None:
            self.session.add(VideoGenerationJobModel(video_job_id=job_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        self._sync_shots(job)

    def _sync_shots(self, job: VideoJob) -> None:
        job_id = UUID(job.job_id)
        organization_id = UUID(job.spec.organization_id)
        encoded = encode_job(job)
        encoded_shots = {
            item["compiled"]["shot_id"]: item for item in encoded["shots"]
        }
        for runtime in job.shots:
            shot_id = runtime.compiled.shot.shot_id
            row = self.session.get(VideoGenerationShotModel, (job_id, shot_id))
            values = {
                "organization_id": organization_id,
                "ordinal": runtime.compiled.index,
                "retry_ordinal": runtime.compiled.retry_ordinal,
                "paid_operation_id": UUID(runtime.compiled.paid_operation_id),
                "status": runtime.status.value,
                "shot_json": encoded_shots[shot_id],
                "validation_json": (
                    encoded_shots[shot_id].get("validation")
                    if runtime.validation is not None
                    else None
                ),
                "artifact_version_id": (
                    UUID(runtime.artifact_version_id)
                    if runtime.artifact_version_id
                    else None
                ),
                "error_code": runtime.error_code,
                "updated_at": datetime.now(UTC),
            }
            if row is None:
                self.session.add(
                    VideoGenerationShotModel(
                        video_job_id=job_id,
                        shot_id=shot_id,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            self.session.flush()
            self._sync_provider(job, runtime)
            self._sync_clip(job, runtime, encoded_shots[shot_id])
            self._sync_cost(job, runtime)

    def _sync_provider(self, job: VideoJob, runtime) -> None:
        job_id = UUID(job.job_id)
        key = (
            job_id,
            runtime.compiled.shot.shot_id,
            runtime.compiled.retry_ordinal,
        )
        row = self.session.get(VideoProviderJobModel, key)
        pending = runtime.pending
        if pending is not None:
            values = {
                "organization_id": UUID(job.spec.organization_id),
                "provider": pending.result.provider,
                "model": pending.result.model,
                "capability": pending.capability,
                "provider_request_id": pending.result.provider_request_id or "unknown",
                "poll_attempts": 0 if row is None else row.poll_attempts + 1,
                "last_polled_at": None if row is None else datetime.now(UTC),
                "terminal_status": self._terminal_status(runtime.status),
                "result_json": {
                    "status": pending.result.status,
                    "provider": pending.result.provider,
                    "model": pending.result.model,
                    "provider_request_id": pending.result.provider_request_id,
                    "pricing_snapshot_id": pending.result.pricing_snapshot_id,
                    "routing_reason_codes": list(
                        pending.result.routing_reason_codes
                    ),
                },
            }
            if row is None:
                self.session.add(
                    VideoProviderJobModel(
                        video_job_id=job_id,
                        shot_id=runtime.compiled.shot.shot_id,
                        retry_ordinal=runtime.compiled.retry_ordinal,
                        **values,
                    )
                )
            else:
                for key_name, value in values.items():
                    setattr(row, key_name, value)
            return
        if row is not None:
            row.terminal_status = self._terminal_status(runtime.status)
            row.last_polled_at = datetime.now(UTC)

    @staticmethod
    def _terminal_status(status: ShotStatus) -> str | None:
        if status is ShotStatus.READY:
            return "COMPLETED"
        if status is ShotStatus.FAILED:
            return "FAILED"
        if status is ShotStatus.CANCELLED:
            return "CANCELLED"
        return None

    def _sync_clip(self, job: VideoJob, runtime, encoded_runtime) -> None:
        if runtime.clip is None:
            return
        job_id = UUID(job.job_id)
        key = (
            job_id,
            runtime.compiled.shot.shot_id,
            runtime.compiled.retry_ordinal,
        )
        row = self.session.get(VideoGenerationClipModel, key)
        clip = runtime.clip
        values = {
            "organization_id": UUID(job.spec.organization_id),
            "artifact_version_id": (
                UUID(runtime.artifact_version_id)
                if runtime.artifact_version_id
                else None
            ),
            "durable_ref": clip.durable_ref,
            "bucket": clip.object.bucket,
            "storage_key": clip.object.storage_key,
            "size_bytes": clip.object.size_bytes,
            "checksum_sha256": clip.checksum_sha256,
            "mime_type": clip.probe.mime_type,
            "width": clip.probe.width,
            "height": clip.probe.height,
            "duration_seconds": clip.probe.duration_seconds,
            "decodable_frames": clip.probe.decodable_frames,
            "black_frame_ratio": clip.probe.black_frame_ratio,
            "clip_json": encoded_runtime["clip"],
        }
        if row is None:
            self.session.add(
                VideoGenerationClipModel(
                    video_job_id=job_id,
                    shot_id=runtime.compiled.shot.shot_id,
                    retry_ordinal=runtime.compiled.retry_ordinal,
                    **values,
                )
            )
        else:
            for key_name, value in values.items():
                setattr(row, key_name, value)

    def _sync_cost(self, job: VideoJob, runtime) -> None:
        provider = None
        model = None
        provider_request_id = None
        pricing_snapshot_id = None
        if runtime.clip is not None:
            provider = runtime.clip.provider
            model = runtime.clip.model
            provider_request_id = runtime.clip.provider_request_id
        elif runtime.pending is not None:
            provider = runtime.pending.result.provider
            model = runtime.pending.result.model
            provider_request_id = runtime.pending.result.provider_request_id
            pricing_snapshot_id = runtime.pending.result.pricing_snapshot_id
        if provider is None or model is None:
            return
        job_id = UUID(job.job_id)
        key = (
            job_id,
            runtime.compiled.shot.shot_id,
            runtime.compiled.retry_ordinal,
        )
        row = self.session.get(VideoGenerationCostProjectionModel, key)
        values = {
            "operation_id": UUID(runtime.compiled.paid_operation_id),
            "provider": provider,
            "model": model,
            "provider_request_id": provider_request_id,
            "amount_usd": runtime.actual_cost_usd,
            "pricing_snapshot_id": pricing_snapshot_id,
            "monetary_owner": "NODE27_MODEL_GATEWAY_SETTLEMENT",
            "recorded_at": datetime.now(UTC),
        }
        if row is None:
            self.session.add(
                VideoGenerationCostProjectionModel(
                    video_job_id=job_id,
                    shot_id=runtime.compiled.shot.shot_id,
                    retry_ordinal=runtime.compiled.retry_ordinal,
                    **values,
                )
            )
        else:
            for key_name, value in values.items():
                setattr(row, key_name, value)

    def claim_webhook(self, provider: str, event_id: str) -> bool:
        if not provider or not event_id:
            raise ValueError("VIDEO_WEBHOOK_IDENTITY_REQUIRED")
        organization_id = self.session.info.get("organization_id")
        if organization_id is None:
            raise ValueError("VIDEO_WEBHOOK_ORGANIZATION_SCOPE_REQUIRED")
        try:
            with self.session.begin_nested():
                self.session.add(
                    VideoWebhookDedupeModel(
                        organization_id=UUID(str(organization_id)),
                        provider=provider,
                        event_id=event_id,
                    )
                )
                self.session.flush()
        except IntegrityError:
            return False
        self.session.commit()
        return True
