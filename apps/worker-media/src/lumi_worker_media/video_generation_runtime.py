from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from lumi_domain.performance_events import PerformanceTelemetryContext
from lumi_video_generation import VideoGenerationPipeline
from lumi_video_generation.model import VideoJob, VideoTaskSpec
from lumi_video_generation.performance_ports import TimedMediaSandbox

from .job_runtime import ExternalWait
from .queue_contracts import JobMessage
from .video_cost_runtime import ScopedPostgresVideoCostObserver
from .video_final_probe_runtime import HostedVerifiedVideoMediaSandbox
from .video_gateway_runtime import HostedVideoGateway
from .video_generation_artifacts import PostgresVideoArtifactAdapter
from .video_generation_codec import decode_video_task_spec
from .video_generation_ports import (
    HostedVideoMediaSandbox,
    HostedVideoOutputAdapter,
    PostgresVideoEventSink,
)
from .video_generation_repository import PostgresVideoRepository
from .video_validation_runtime import HostedV1VideoValidator

_TASK_INPUT_SCHEMA_VERSION = 1
_JOB_KIND = "video.render"
_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_DEFAULT_POLL_SECONDS = 15
_MIN_POLL_SECONDS = 5
_MAX_POLL_SECONDS = 300


class HostedVideoGenerationError(RuntimeError):
    retryable = False

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class HostedVideoGenerationRuntime:
    """Production composition root for durable NODE-48 video.render execution.

    V1 intentionally exposes only single-shot text-to-video. Provider work is async
    behind the private Model Gateway. Each Worker invocation hydrates one PostgreSQL
    UoW, advances the NODE-48 state machine once, flushes its recovery snapshot, and
    parks the canonical Task as waiting_external when the provider is still pending.
    """

    def __init__(
        self,
        *,
        database_dsn: str,
        asset_bucket: str,
        poll_seconds: int,
    ) -> None:
        self.database_dsn = _asyncpg_dsn(database_dsn)
        if not asset_bucket or asset_bucket != asset_bucket.strip() or "/" in asset_bucket:
            raise ValueError("VIDEO_RUNTIME_ASSET_BUCKET_INVALID")
        if not _MIN_POLL_SECONDS <= poll_seconds <= _MAX_POLL_SECONDS:
            raise ValueError("VIDEO_RUNTIME_POLL_INTERVAL_INVALID")
        self.asset_bucket = asset_bucket
        self.poll_seconds = poll_seconds

    @classmethod
    def from_env(cls) -> HostedVideoGenerationRuntime:
        profile = _required_env("LUMI_VIDEO_MODEL_PROFILE", max_length=100)
        if not _PROFILE.fullmatch(profile):
            raise RuntimeError("LUMI_VIDEO_MODEL_PROFILE_INVALID")
        # Fail fast on every private dependency/credential binding at process boot.
        HostedVideoGateway.from_env()
        HostedVideoOutputAdapter.from_env()
        return cls(
            database_dsn=_required_env("LUMI_DATABASE_URL", max_length=8192),
            asset_bucket=_required_env("LUMI_S3_BUCKET", max_length=255),
            poll_seconds=_bounded_int_env(
                "LUMI_VIDEO_PROVIDER_POLL_SECONDS",
                default=_DEFAULT_POLL_SECONDS,
                minimum=_MIN_POLL_SECONDS,
                maximum=_MAX_POLL_SECONDS,
            ),
        )

    async def execute(self, message: JobMessage) -> dict[str, Any] | ExternalWait:
        telemetry = PerformanceTelemetryContext.from_environ()
        spec = await self._load_spec(message)
        _validate_hosted_v1_spec(spec)

        repository = PostgresVideoRepository(self.database_dsn)
        existing = await repository.load(
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
        )
        gateway = HostedVideoGateway.from_env()
        output = HostedVideoOutputAdapter.from_env()
        base_sandbox = HostedVideoMediaSandbox.from_spec(spec)
        sandbox = HostedVerifiedVideoMediaSandbox(
            spec=spec,
            renderer=base_sandbox,
            probe_adapter=output,
        )
        pipeline = VideoGenerationPipeline(
            repository=repository,
            gateway=gateway,
            output=output,
            validator=HostedV1VideoValidator(),
            artifacts=PostgresVideoArtifactAdapter(
                self.database_dsn,
                bucket=self.asset_bucket,
            ),
            sandbox=TimedMediaSandbox(
                sandbox,
                telemetry,
                operation_id=spec.operation_id,
                task_id=spec.task_id,
            ),
            costs=ScopedPostgresVideoCostObserver(self.database_dsn),
            events=PostgresVideoEventSink(self.database_dsn),
        )

        if existing is None:
            job = await pipeline.start(spec)
        else:
            job = await pipeline.resume(
                organization_id=spec.organization_id,
                video_job_id=existing.video_job_id,
            )

        persisted = await repository.flush(
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
        )
        if persisted != job:
            raise HostedVideoGenerationError(
                "VIDEO_RUNTIME_FLUSH_RESULT_MISMATCH",
                "durable video snapshot changed during flush",
            )
        if job.status == "WAITING_EXTERNAL":
            waiting = [item for item in job.shots if item.status == "WAITING_EXTERNAL"]
            if len(waiting) != 1:
                raise HostedVideoGenerationError("VIDEO_RUNTIME_WAITING_SHOT_INVALID")
            shot = waiting[0]
            if not shot.provider_request_id:
                raise HostedVideoGenerationError("VIDEO_RUNTIME_PROVIDER_REQUEST_ID_MISSING")
            wait_ref = hashlib.sha256(
                (
                    f"{job.video_job_id}\x00{shot.shot_id}\x00"
                    f"{shot.provider_request_id}"
                ).encode("utf-8")
            ).hexdigest()
            return ExternalWait(
                wait_reason="video_provider_pending",
                external_ref=f"video-provider:{wait_ref}",
                retry_not_before=datetime.now(UTC) + timedelta(seconds=self.poll_seconds),
                output=_task_output(job),
            )
        if job.status in {"FAILED", "CANCELLED"}:
            raise HostedVideoGenerationError(
                job.error_code or f"VIDEO_GENERATION_{job.status}",
                f"video generation ended in {job.status.lower()}",
            )
        if job.status not in {"COMPLETED", "PARTIAL"}:
            raise HostedVideoGenerationError(
                "VIDEO_RUNTIME_NONTERMINAL_WITHOUT_EXTERNAL_WAIT",
                f"unexpected video job state: {job.status}",
            )
        return _task_output(job)

    async def _load_spec(self, message: JobMessage) -> VideoTaskSpec:
        connection = await asyncpg.connect(self.database_dsn)
        try:
            row = await connection.fetchrow(
                """
                SELECT type, input_json
                FROM tasks
                WHERE id=$1 AND organization_id=$2 AND project_id=$3
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
        finally:
            await connection.close()
        if row is None:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_NOT_FOUND")
        if row["type"] != _JOB_KIND:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_TYPE_MISMATCH")
        payload = _json_object(row["input_json"])
        if set(payload) != {"schema_version", "job_kind", "video_generation_spec"}:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_INPUT_FIELDS_INVALID")
        if payload.get("schema_version") != _TASK_INPUT_SCHEMA_VERSION:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_INPUT_SCHEMA_UNSUPPORTED")
        if payload.get("job_kind") != _JOB_KIND:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_INPUT_KIND_MISMATCH")
        raw_spec = payload.get("video_generation_spec")
        if not isinstance(raw_spec, dict):
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_SPEC_MISSING")
        try:
            spec = decode_video_task_spec(raw_spec)
        except (TypeError, ValueError) as exc:
            raise HostedVideoGenerationError(
                "VIDEO_GENERATION_TASK_SPEC_INVALID",
                str(exc),
            ) from exc
        if UUID(spec.organization_id) != message.organization_id:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_ORGANIZATION_MISMATCH")
        if UUID(spec.project_id) != message.project_id:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_PROJECT_MISMATCH")
        if UUID(spec.task_id) != message.job_id:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_ID_MISMATCH")
        if message.operation_id is None or UUID(spec.operation_id) != message.operation_id:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_OPERATION_MISMATCH")
        return spec


def _validate_hosted_v1_spec(spec: VideoTaskSpec) -> None:
    if spec.mode != "TEXT_TO_VIDEO":
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_TEXT_TO_VIDEO_ONLY")
    if spec.source_images:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_SOURCE_IMAGE_UNSUPPORTED")
    if spec.audio_tracks:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_AUDIO_TRACK_UNSUPPORTED")
    if spec.identity_requirements:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_IDENTITY_VALIDATION_UNAVAILABLE")
    if spec.brand_rule_set_version is not None:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_BRAND_VALIDATION_UNAVAILABLE")
    if spec.seed is not None:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_SEED_UNSUPPORTED")
    if len(spec.shots) > 1:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_SINGLE_SHOT_ONLY")
    if spec.shots:
        shot = spec.shots[0]
        if shot.source_ref is not None or shot.continuity_refs:
            raise HostedVideoGenerationError("VIDEO_HOSTED_V1_REFERENCE_INPUT_UNSUPPORTED")
        if shot.optional:
            raise HostedVideoGenerationError("VIDEO_HOSTED_V1_OPTIONAL_SHOT_UNSUPPORTED")
        if shot.transition_to_next != "CUT":
            raise HostedVideoGenerationError("VIDEO_HOSTED_V1_TRANSITION_UNSUPPORTED")
    seconds = spec.duration_seconds
    if seconds != seconds.to_integral_value() or int(seconds) not in {4, 8, 12}:
        raise HostedVideoGenerationError("VIDEO_HOSTED_V1_DURATION_UNSUPPORTED")


def _task_output(job: VideoJob) -> dict[str, Any]:
    return {
        "video_job_id": job.video_job_id,
        "status": job.status,
        "operation_id": job.operation_id,
        "estimated_cost_usd": format(job.estimated_cost_usd, "f"),
        "actual_cost_usd": format(job.actual_cost_usd, "f"),
        "final_artifact_version_id": job.final_artifact_version_id,
        "error_code": job.error_code,
        "shots": [
            {
                "shot_id": item.shot_id,
                "status": item.status,
                "attempt_count": item.attempt_count,
                "artifact_version_id": item.clip_artifact_version_id,
                "error_code": item.error_code,
            }
            for item in job.shots
        ],
    }


def encode_task_input(spec: VideoTaskSpec) -> dict[str, Any]:
    from .video_generation_codec import encode_video_task_spec

    return {
        "schema_version": _TASK_INPUT_SCHEMA_VERSION,
        "job_kind": _JOB_KIND,
        "video_generation_spec": encode_video_task_spec(spec),
    }


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_INPUT_INVALID") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise HostedVideoGenerationError("VIDEO_GENERATION_TASK_INPUT_INVALID")
    return value


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _bounded_int_env(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name}_INVALID") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name}_OUT_OF_RANGE")
    return value


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("VIDEO_DATABASE_URL_MUST_USE_POSTGRESQL")


__all__ = [
    "HostedVideoGenerationError",
    "HostedVideoGenerationRuntime",
    "encode_task_input",
]
