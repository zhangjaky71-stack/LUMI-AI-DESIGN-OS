from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing required contract marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden contract marker: {needle}")


def main() -> int:
    require(
        "services/domain/src/lumi_domain/job_dispatch.py",
        "MAX_JOB_MESSAGE_BYTES = 64 * 1024",
        'JOB_DISPATCH_EVENT_NAME = "job.dispatch.requested"',
        'IMAGE_TRANSFORM_TASK_NAME = "lumi.jobs.image.transform"',
        'IMAGE_TRANSFORM_QUEUE = "lumi.media.image"',
        'IMAGE_TRANSFORM_ROUTING_KEY = "image.transform"',
        "class JobMessage",
        "class JobDispatch",
        "JOB_MESSAGE_UNKNOWN_FIELDS",
        "JOB_MESSAGE_BINARY_FORBIDDEN",
        "JOB_MESSAGE_SECRET_FIELD_FORBIDDEN",
        "JOB_MESSAGE_TOO_LARGE",
        '"args": [self.message.as_dict()]',
        '"kwargs": {}',
    )
    require(
        "apps/worker-media/src/lumi_worker_media/queue_contracts.py",
        "from lumi_domain.job_dispatch import MAX_JOB_MESSAGE_BYTES, JobMessage, validate_job_payload",
        'JobKind.IMAGE_TRANSFORM: "lumi.media.image"',
    )
    require(
        "apps/worker-media/src/lumi_worker_media/app.py",
        'name="lumi.jobs.image.transform"',
        "def image_transform(self: object, message: dict[str, object])",
        "parsed = JobMessage.from_mapping(message)",
    )
    require(
        "apps/api/src/lumi_api/media_dispatch.py",
        "IMAGE_TRANSFORM_TASK_NAME",
        "IMAGE_TRANSFORM_QUEUE",
        "JOB_DISPATCH_EVENT_NAME",
        "JobDispatch",
        "generation.task_id != task_id",
        "MEDIA_DISPATCH_GENERATION_ORGANIZATION_MISMATCH",
        "MEDIA_DISPATCH_GENERATION_PROJECT_MISMATCH",
        "MEDIA_DISPATCH_GENERATION_OPERATION_REQUIRED",
        "MEDIA_DISPATCH_GENERATION_SPEC_MISMATCH",
        "session.add(event)",
        "never touch the broker",
    )
    forbid(
        "apps/api/src/lumi_api/media_dispatch.py",
        "from celery",
        "import celery",
        ".send_task(",
        "MediaTaskBroker",
        "publish_media_outbox_event",
        "api_key",
        "access_token",
        "provider_secret",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/event_runtime.py",
        "event_name <> $2",
        "JOB_DISPATCH_EVENT_NAME",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py",
        "class MediaJobOutboxDispatcher",
        "event_name = $2",
        "FOR UPDATE SKIP LOCKED",
        "publish_attempts = publish_attempts + 1",
        "SET published_at = now()",
        "await asyncio.to_thread(self.publisher.publish, dispatch)",
        "if failure is not None",
        "IMAGE_TRANSFORM_ROUTING_KEY",
        "exchange=JOBS_EXCHANGE.name",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/cli.py",
        "MediaJobOutboxDispatcher",
        "CeleryJobPublisher",
        "job_published = await job_dispatcher.dispatch_batch",
        "domain_published = await domain_dispatcher.dispatch_batch",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/platform.py",
        "class OutboxEvent",
        "publish_attempts",
        "published_at",
    )
    require(
        "apps/api/pyproject.toml",
        '"lumi-domain"',
        '"lumi-image-generation"',
    )
    require(
        "apps/worker-media/pyproject.toml",
        '"lumi-domain"',
    )
    print("NODE-73.1 canonical media dispatch contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
