from __future__ import annotations

import ast
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


def _celery_task_function(path: str, function_name: str, task_name: str) -> ast.FunctionDef:
    source_path = ROOT / path
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        ),
        None,
    )
    if function is None:
        raise SystemExit(f"{path}: missing task function: {function_name}")

    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute) or decorator.func.attr != "task":
            continue
        for keyword in decorator.keywords:
            if (
                keyword.arg == "name"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == task_name
            ):
                return function
    raise SystemExit(f"{path}: {function_name} is not registered as {task_name}")


def _forbid_task_string(function: ast.FunctionDef, value: str, *, path: str) -> None:
    if any(
        isinstance(node, ast.Constant) and node.value == value
        for node in ast.walk(function)
    ):
        raise SystemExit(f"{path}: {function.name} contains forbidden placeholder: {value}")


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
        "class DomainOutboxHealth",
        "FOR UPDATE SKIP LOCKED",
        "ON CONFLICT (consumer, event_id) DO NOTHING",
        "publish_attempts =",
        "published_at = now()",
        "event_name <> $2",
        "event_name <> $1",
        "JOB_DISPATCH_EVENT_NAME",
        "failure: Exception | None = None",
        "failure = exc",
        "if failure is not None:",
        "async def health_snapshot(self) -> DomainOutboxHealth:",
        "ORDER BY created_at, id",
        "LIMIT 1",
        "message.reject(requeue=False)",
        "dead_letter_records",
    )
    require(
        "services/domain/src/lumi_domain/job_dispatch.py",
        "MAX_JOB_MESSAGE_BYTES = 64 * 1024",
        'JOB_DISPATCH_EVENT_NAME = "job.dispatch.requested"',
        'IMAGE_TRANSFORM_TASK_NAME = "lumi.jobs.image.transform"',
        'IMAGE_TRANSFORM_QUEUE = "lumi.media.image"',
        'IMAGE_TRANSFORM_ROUTING_KEY = "image.transform"',
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
        "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py",
        "class MediaJobOutboxDispatcher",
        "event_name = $2",
        "FOR UPDATE SKIP LOCKED",
        "publish_attempts = publish_attempts + 1",
        "SET published_at = now()",
        "await asyncio.to_thread(self.publisher.publish, dispatch)",
        "if failure is not None",
        "async def health_snapshot(self) -> MediaJobOutboxHealth:",
        "exchange=JOBS_EXCHANGE.name",
        "_ROUTE_BY_TASK: dict[str, tuple[str, str]]",
        "IMAGE_TRANSFORM_TASK_NAME: (IMAGE_TRANSFORM_QUEUE, IMAGE_TRANSFORM_ROUTING_KEY)",
        "VIDEO_RENDER_TASK_NAME: (VIDEO_RENDER_QUEUE, VIDEO_RENDER_ROUTING_KEY)",
        "routing_key = _validate_media_dispatch(dispatch)",
        "routing_key=routing_key",
    )
    app_path = "apps/worker-media/src/lumi_worker_media/app.py"
    require(
        app_path,
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
    image_task = _celery_task_function(
        app_path,
        "image_transform",
        "lumi.jobs.image.transform",
    )
    _celery_task_function(
        app_path,
        "video_render",
        "lumi.jobs.video.render",
    )
    _forbid_task_string(image_task, "accepted", path=app_path)
    require(
        "apps/worker-media/src/lumi_worker_media/task_base.py",
        "RuntimeTask",
        "DeadLetterStore",
        'message_kind="job"',
        "<redacted>",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/cli.py",
        "dispatch-outbox",
        "MediaJobOutboxDispatcher",
        "CeleryJobPublisher",
        "failures: list[tuple[str, Exception]] = []",
        "job_published = await job_dispatcher.dispatch_batch",
        "domain_published = await domain_dispatcher.dispatch_batch",
        "job_health = await job_dispatcher.health_snapshot()",
        "domain_health = await domain_dispatcher.health_snapshot()",
        'failures.append(("jobs", exc))',
        'failures.append(("domain", exc))',
        'failures.append(("jobs-health", exc))',
        'failures.append(("domain-health", exc))',
        "oldest_unpublished_age_seconds = max(",
        "oldest_publish_attempts = max(",
        '"oldest_domain_unpublished_age_seconds"',
        '"oldest_job_unpublished_age_seconds"',
        "OUTBOX_DISPATCH_FAILED",
        "replay-dead-letter",
        "DEAD_LETTER_ALREADY_REPLAYED",
    )
    require(
        "apps/worker-media/tests/test_queue_cli.py",
        "test_domain_dispatch_still_runs_when_job_dispatch_fails",
        "MediaJobOutboxHealth",
        "DomainOutboxHealth",
        "async def health_snapshot",
        'assert calls == ["wake", "jobs", "domain"]',
        "OUTBOX_DISPATCH_FAILED:jobs",
    )
    require(
        "apps/worker-media/tests/test_job_dispatch_observability.py",
        "test_domain_outbox_failed_publish_attempt_commits_before_fail_closed",
        "assert connection.transaction_state.committed is True",
        "assert connection.transaction_state.exc_type is None",
        "test_domain_dispatch_health_reads_only_oldest_pending_row",
        "test_dispatch_cli_emits_bounded_combined_json_health_before_failure",
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
