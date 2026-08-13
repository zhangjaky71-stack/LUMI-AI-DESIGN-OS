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
        "apps/worker-media/src/lumi_worker_media/queue_contracts.py",
        "MAX_JOB_MESSAGE_BYTES = 64 * 1024",
        "JOB_MESSAGE_BINARY_FORBIDDEN",
        "JOB_MESSAGE_SECRET_FIELD_FORBIDDEN",
        "provider_reconciliation_required=True",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/app.py",
        "task_acks_late=False",
        "task_reject_on_worker_lost=False",
        '"lumi.assets.validate"',
    )
    forbid(
        "apps/worker-media/src/lumi_worker_media/app.py",
        "task_acks_late=True",
        "task_reject_on_worker_lost=True",
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
