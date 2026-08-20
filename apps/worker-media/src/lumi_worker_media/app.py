from __future__ import annotations

import asyncio
import os
from uuid import UUID

from celery import Celery
from lumi_asset_storage.s3 import S3ObjectStore

from .asset_config import AssetWorkerSettings
from .asset_validation import validate_asset_run
from .image_generation_runtime import HostedImageGenerationRuntime
from .job_runtime import JobOutcome, TaskJobStore, execute_job
from .queue_contracts import JobKind, JobMessage, JobState, queue_for, retry_policy_for
from .task_base import RuntimeTask
from .topology import build_job_queues
from .video_generation_runtime import HostedVideoGenerationRuntime

broker = os.getenv("LUMI_RABBITMQ_URL") or os.getenv("RABBITMQ_URL", "memory://")
configured_backend = os.getenv("CELERY_RESULT_BACKEND")
backend = configured_backend or ("cache+memory://" if broker == "memory://" else None)
celery_app = Celery("lumi-worker-media", broker=broker, backend=backend)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_queues=tuple(build_job_queues()),
    task_default_exchange="lumi.jobs",
    task_default_exchange_type="direct",
    task_default_routing_key="image.transform",
    worker_prefetch_multiplier=1,
    task_acks_late=False,
    task_reject_on_worker_lost=False,
    task_track_started=True,
)
celery_app.conf.task_routes = {
    "lumi.jobs.image.transform": {"queue": queue_for(JobKind.IMAGE_TRANSFORM)},
    "lumi.jobs.video.render": {"queue": queue_for(JobKind.VIDEO_RENDER)},
    "lumi.jobs.asset.preview": {"queue": queue_for(JobKind.ASSET_PREVIEW)},
    "lumi.assets.validate": {"queue": queue_for(JobKind.ASSET_VALIDATE)},
    "lumi.jobs.export.package": {"queue": queue_for(JobKind.EXPORT_PACKAGE)},
}


def health_payload() -> dict[str, str]:
    return {"service": "worker-media", "status": "ok", "version": "0.0.0-dev"}


@celery_app.task(name="health.ping")
def health_ping() -> dict[str, str]:
    return health_payload()


@celery_app.task(
    name="lumi.jobs.image.transform",
    bind=True,
    max_retries=3,
    base=RuntimeTask,
)
def image_transform(self: object, message: dict[str, object]) -> dict[str, object]:
    parsed = JobMessage.from_mapping(message)
    outcome = asyncio.run(_execute_image_generation_job(parsed))
    if outcome.state == JobState.RETRYING:
        retries = getattr(getattr(self, "request", None), "retries", 0)
        policy = retry_policy_for(JobKind.IMAGE_TRANSFORM)
        retry = getattr(self, "retry")
        countdown = policy.delay_seconds(
            attempt=max(1, outcome.attempt_count),
            jitter_seed=retries,
        )
        raise retry(
            exc=RuntimeError(str(outcome.output.get("error", "IMAGE_GENERATION_RETRY"))),
            countdown=countdown,
        )
    if outcome.state == JobState.FAILED:
        raise RuntimeError(
            "IMAGE_GENERATION_JOB_FAILED:"
            + str(outcome.output.get("error", "unknown"))[:1000]
        )
    return {
        "job_id": str(parsed.job_id),
        "state": outcome.state.value,
        "attempt_count": outcome.attempt_count,
        **outcome.output,
    }


async def _execute_image_generation_job(message: JobMessage) -> JobOutcome:
    runtime = HostedImageGenerationRuntime.from_env()
    store = TaskJobStore(_database_dsn())
    return await execute_job(
        store=store,
        message=message,
        handler=runtime.execute,
    )


@celery_app.task(
    name="lumi.jobs.video.render",
    bind=True,
    max_retries=2,
    base=RuntimeTask,
)
def video_render(self: object, message: dict[str, object]) -> dict[str, object]:
    parsed = JobMessage.from_mapping(message)
    outcome = asyncio.run(_execute_video_generation_job(parsed))
    if outcome.state == JobState.RETRYING:
        retries = getattr(getattr(self, "request", None), "retries", 0)
        policy = retry_policy_for(JobKind.VIDEO_RENDER)
        retry = getattr(self, "retry")
        countdown = policy.delay_seconds(
            attempt=max(1, outcome.attempt_count),
            jitter_seed=retries,
        )
        raise retry(
            exc=RuntimeError(str(outcome.output.get("error", "VIDEO_GENERATION_RETRY"))),
            countdown=countdown,
        )
    if outcome.state == JobState.FAILED:
        raise RuntimeError(
            "VIDEO_GENERATION_JOB_FAILED:"
            + str(outcome.output.get("error", "unknown"))[:1000]
        )
    return {
        "job_id": str(parsed.job_id),
        "state": outcome.state.value,
        "attempt_count": outcome.attempt_count,
        **outcome.output,
    }


async def _execute_video_generation_job(message: JobMessage) -> JobOutcome:
    runtime = HostedVideoGenerationRuntime.from_env()
    store = TaskJobStore(_database_dsn())
    return await execute_job(
        store=store,
        message=message,
        handler=runtime.execute,
    )


@celery_app.task(name="lumi.jobs.asset.preview", base=RuntimeTask)
def asset_preview(message: dict[str, object]) -> dict[str, object]:
    parsed = JobMessage.from_mapping(message)
    return {"job_id": str(parsed.job_id), "status": "accepted", "kind": JobKind.ASSET_PREVIEW}


@celery_app.task(name="lumi.jobs.export.package", base=RuntimeTask)
def export_package(message: dict[str, object]) -> dict[str, object]:
    parsed = JobMessage.from_mapping(message)
    return {"job_id": str(parsed.job_id), "status": "accepted", "kind": JobKind.EXPORT_PACKAGE}


@celery_app.task(name="lumi.assets.validate", bind=True, max_retries=4, base=RuntimeTask)
def asset_validate(self: object, validation_run_id: str) -> str:
    settings = AssetWorkerSettings()
    object_store = S3ObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        force_path_style=settings.s3_force_path_style,
    )
    try:
        return asyncio.run(
            validate_asset_run(
                UUID(validation_run_id),
                settings=settings,
                object_store=object_store,
            )
        )
    except Exception as exc:
        retries = getattr(getattr(self, "request", None), "retries", 0)
        policy = retry_policy_for(JobKind.ASSET_VALIDATE)
        if retries >= policy.max_attempts - 1:
            raise
        retry = getattr(self, "retry")
        countdown = policy.delay_seconds(attempt=retries + 1, jitter_seed=retries)
        raise retry(exc=exc, countdown=countdown)


def _database_dsn() -> str:
    value = os.getenv("LUMI_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("LUMI_DATABASE_URL_REQUIRED")
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql://" + value[len("postgresql+asyncpg://") :]
    if value.startswith("postgresql://"):
        return value
    raise RuntimeError("LUMI_DATABASE_URL_MUST_USE_POSTGRESQL")
