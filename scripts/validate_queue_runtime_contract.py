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
        "apps/worker-media/src/lumi_worker_media/topology.py",
        'Exchange("lumi.jobs", type="direct"',
        'Exchange("lumi.domain", type="topic"',
        'Exchange("lumi.dlx", type="topic"',
        '"lumi.media.image"',
        '"lumi.media.video"',
        '"lumi.media.export"',
        '"lumi.asset.processing"',
        '"x-dead-letter-exchange"',
    )
    require(
        "apps/worker-media/src/lumi_worker_media/event_runtime.py",
        "FOR UPDATE SKIP LOCKED",
        "ON CONFLICT (consumer, event_id) DO NOTHING",
        "publish_attempts =",
        "published_at = now()",
        "message.reject(requeue=False)",
        "dead_letter_records",
    )
    require(
        "services/domain/src/lumi_domain/job_dispatch.py",
        "MAX_JOB_MESSAGE_BYTES = 64 * 1024",
        "JOB_MESSAGE_BINARY_FORBIDDEN",
        "JOB_MESSAGE_SECRET_FIELD_FORBIDDEN",
        'allowed = {"job_id", "organization_id", "project_id", "operation_id", "trace_id"}',
    )
    require(
        "apps/worker-media/src/lumi_worker_media/queue_contracts.py",
        "from lumi_domain.job_dispatch import MAX_JOB_MESSAGE_BYTES, JobMessage, validate_job_payload",
        "provider_reconciliation_required=True",
        'JobKind.IMAGE_TRANSFORM: "lumi.media.image"',
    )
    require(
        "apps/worker-media/src/lumi_worker_media/app.py",
        "task_acks_late=False",
        "task_reject_on_worker_lost=False",
        '"lumi.assets.validate"',
        'name="lumi.jobs.image.transform"',
        "_execute_image_generation_job(parsed)",
        "HostedImageGenerationRuntime.from_env()",
        "TaskJobStore(_database_dsn())",
        "handler=runtime.execute",
        "outcome.state == JobState.RETRYING",
        "outcome.state == JobState.FAILED",
        'os.getenv("LUMI_DATABASE_URL")',
    )
    app = (ROOT / "apps/worker-media/src/lumi_worker_media/app.py").read_text(encoding="utf-8")
    image_start = app.index('name="lumi.jobs.image.transform"')
    video_start = app.index('@celery_app.task(name="lumi.jobs.video.render"')
    image_block = app[image_start:video_start]
    if '"status": "accepted"' in image_block:
        raise SystemExit(
            "apps/worker-media/src/lumi_worker_media/app.py: "
            "image.transform must not regress to accepted placeholder"
        )
    require(
        "apps/worker-media/src/lumi_worker_media/task_base.py",
        "RuntimeTask",
        "DeadLetterStore",
        'message_kind="job"',
        "<redacted>",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/cli.py",
        "replay-dead-letter",
        "DEAD_LETTER_ALREADY_REPLAYED",
    )
    require(
        "apps/api/alembic/versions/0008_queue_event_runtime.py",
        "CREATE TABLE dead_letter_records",
        "GRANT SELECT, INSERT, UPDATE ON dead_letter_records TO lumi_app",
    )
    print("NODE-19 queue/event runtime contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
