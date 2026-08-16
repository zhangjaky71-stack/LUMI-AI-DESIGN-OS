from __future__ import annotations

import os
from typing import Any, Callable

from celery import Celery

from .job_runtime import JobExecutionResult, execute_job
from .postgres_runtime import PostgresJobStore
from .queue_contracts import (
    JobKind,
    JobMessage,
    JobState,
    queue_for,
    retry_policy_for,
    routing_key_for,
)
from .topology import build_job_queues

broker = os.getenv("RABBITMQ_URL", "memory://")
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
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=False,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"confirm_publish": True},
)

_TASK_NAME_BY_KIND = {
    JobKind.IMAGE_TRANSFORM: "lumi.jobs.image.transform",
    JobKind.VIDEO_RENDER: "lumi.jobs.video.render",
    JobKind.ASSET_PREVIEW: "lumi.jobs.asset.preview",
    JobKind.ASSET_VALIDATE: "lumi.jobs.asset.validate",
    JobKind.EXPORT_PACKAGE: "lumi.jobs.export.package",
}

celery_app.conf.task_routes = {
    task_name: {
        "queue": queue_for(kind),
        "routing_key": routing_key_for(kind),
    }
    for kind, task_name in _TASK_NAME_BY_KIND.items()
}


def health_payload() -> dict[str, str]:
    return {"service": "worker-media", "status": "ok", "version": "0.0.0-dev"}


@celery_app.task(name="health.ping")
def health_ping() -> dict[str, str]:
    return health_payload()


def submit_job(kind: JobKind, message: JobMessage, *, countdown: int | None = None) -> Any:
    options: dict[str, Any] = {
        "queue": queue_for(kind),
        "routing_key": routing_key_for(kind),
    }
    if countdown is not None:
        options["countdown"] = countdown
    return celery_app.send_task(
        _TASK_NAME_BY_KIND[kind],
        args=[message.as_dict()],
        **options,
    )


def _runtime_handler(kind: JobKind) -> Callable[[JobMessage], dict[str, Any]]:
    def handler(message: JobMessage) -> dict[str, Any]:
        return {
            "job_id": str(message.job_id),
            "kind": kind.value,
            "status": "processed",
            "resource_id": str(message.resource_id) if message.resource_id else None,
        }

    return handler


def _execute_bound_task(task: Any, kind: JobKind, payload: dict[str, Any]) -> dict[str, Any]:
    message = JobMessage.from_mapping(payload)
    dsn = os.getenv("LUMI_RUNTIME_DATABASE_URL")
    if not dsn:
        return _runtime_handler(kind)(message)
    store = PostgresJobStore(dsn)
    result: JobExecutionResult = execute_job(
        store=store,
        message=message,
        kind=kind,
        handler=_runtime_handler(kind),
    )
    if result.record.state is JobState.RETRYING:
        policy = retry_policy_for(kind)
        raise task.retry(
            countdown=result.retry_in_seconds or policy.base_delay_seconds,
            max_retries=policy.max_attempts - 1,
        )
    if result.record.state is JobState.FAILED:
        raise RuntimeError(result.record.error_code or "JOB_FAILED")
    return result.record.output or {
        "job_id": str(message.job_id),
        "status": result.record.state.value,
    }


@celery_app.task(name="lumi.jobs.image.transform", bind=True)
def image_transform(self: Any, message: dict[str, Any]) -> dict[str, Any]:
    return _execute_bound_task(self, JobKind.IMAGE_TRANSFORM, message)


@celery_app.task(name="lumi.jobs.video.render", bind=True)
def video_render(self: Any, message: dict[str, Any]) -> dict[str, Any]:
    return _execute_bound_task(self, JobKind.VIDEO_RENDER, message)


@celery_app.task(name="lumi.jobs.asset.preview", bind=True)
def asset_preview(self: Any, message: dict[str, Any]) -> dict[str, Any]:
    return _execute_bound_task(self, JobKind.ASSET_PREVIEW, message)


@celery_app.task(name="lumi.jobs.asset.validate", bind=True)
def asset_validate(self: Any, message: dict[str, Any]) -> dict[str, Any]:
    return _execute_bound_task(self, JobKind.ASSET_VALIDATE, message)


@celery_app.task(name="lumi.jobs.export.package", bind=True)
def export_package(self: Any, message: dict[str, Any]) -> dict[str, Any]:
    return _execute_bound_task(self, JobKind.EXPORT_PACKAGE, message)
