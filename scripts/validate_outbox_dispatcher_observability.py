#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py"
CLI = ROOT / "apps/worker-media/src/lumi_worker_media/cli.py"
TEST = ROOT / "apps/worker-media/tests/test_job_dispatch_observability.py"
STAGING_IAC = ROOT / "infra/iac/environments/staging/app/outbox_observability.tf"
PRODUCTION_IAC = ROOT / "infra/iac/environments/production/app/outbox_observability.tf"
STAGING_APP = ROOT / "infra/iac/environments/staging/app/main.tf"
PRODUCTION_APP = ROOT / "infra/iac/environments/production/app/main.tf"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
PRODUCTION_IAC_WORKFLOW = ROOT / ".github/workflows/production-iac-contract.yml"
FINAL_WORKFLOW = ROOT / ".github/workflows/final-acceptance-gate.yml"
SELF_PATH = "scripts/validate_outbox_dispatcher_observability.py"


class OutboxObservabilityContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OutboxObservabilityContractError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{label} missing markers: {missing}")


def python_syntax(source: str, path: Path) -> None:
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        raise OutboxObservabilityContractError(
            f"{path.relative_to(ROOT)} has invalid syntax: {exc}"
        ) from exc


def service_block(source: str, service: str) -> str:
    marker = f"    {service} = {{"
    start = source.find(marker)
    require(start >= 0, f"missing service block: {service}")
    brace = source.find("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise OutboxObservabilityContractError(f"unterminated service block: {service}")


def validate_environment_iac(source: str, *, environment: str) -> None:
    require_markers(
        source,
        (
            'outbox_dispatcher_metric_namespace = "LUMI/MediaDispatch"',
            'resource "aws_cloudwatch_log_metric_filter" "outbox_oldest_unpublished_age"',
            'resource "aws_cloudwatch_log_metric_filter" "outbox_oldest_publish_attempts"',
            'pattern        = "{ $.kind = \\"lumi.outbox_dispatcher.health\\" }"',
            'value         = "$.oldest_unpublished_age_seconds"',
            'value         = "$.oldest_publish_attempts"',
            'resource "aws_cloudwatch_metric_alarm" "outbox_oldest_unpublished_age"',
            'resource "aws_cloudwatch_metric_alarm" "outbox_oldest_publish_attempts"',
            'threshold           = 300',
            'threshold           = 5',
            'statistic           = "Maximum"',
            'treat_missing_data  = "notBreaching"',
            'depends_on = [module.platform_app]',
        ),
        f"{environment} outbox observability IaC",
    )
    require(
        source.count('resource "aws_cloudwatch_log_metric_filter"') == 2,
        f"{environment} must define exactly two outbox log metric filters",
    )
    require(
        source.count('resource "aws_cloudwatch_metric_alarm"') == 2,
        f"{environment} must define exactly two outbox operational alarms",
    )


def main() -> int:
    runtime = read(RUNTIME)
    cli = read(CLI)
    tests = read(TEST)
    staging_iac = read(STAGING_IAC)
    production_iac = read(PRODUCTION_IAC)
    staging_app = read(STAGING_APP)
    production_app = read(PRODUCTION_APP)
    video_workflow = read(VIDEO_WORKFLOW)
    production_iac_workflow = read(PRODUCTION_IAC_WORKFLOW)
    final_workflow = read(FINAL_WORKFLOW)

    for source, path in ((runtime, RUNTIME), (cli, CLI), (tests, TEST)):
        python_syntax(source, path)

    require_markers(
        runtime,
        (
            "class MediaJobOutboxHealth",
            "async def health_snapshot(self) -> MediaJobOutboxHealth:",
            "Read only the oldest pending job row; never count or scan the full outbox.",
            "EXTRACT(EPOCH FROM (now() - created_at))",
            "publish_attempts AS oldest_publish_attempts",
            "WHERE published_at IS NULL",
            "event_name = $1",
            "ORDER BY created_at, id",
            "LIMIT 1",
        ),
        "job dispatcher health query",
    )
    health_start = runtime.find("    async def health_snapshot(")
    validator_start = runtime.find("\ndef _validate_media_dispatch", health_start)
    require(
        health_start >= 0 and validator_start > health_start,
        "job dispatcher health query boundary is missing",
    )
    health_block = runtime[health_start:validator_start]
    require(
        "COUNT(" not in health_block.upper(),
        "outbox health must not count/scan the full pending queue every loop",
    )
    require("FOR UPDATE" not in health_block, "outbox health must remain read-only")

    require_markers(
        cli,
        (
            '_HEALTH_LOG_KIND = "lumi.outbox_dispatcher.health"',
            "job_health = await job_dispatcher.health_snapshot()",
            '"oldest_unpublished_age_seconds"',
            '"oldest_publish_attempts"',
            '"failure_channels": channels',
            '"failure_count": len(failures)',
            '"status": "degraded" if failures else "ok"',
            "json.dumps(",
            "flush=True",
            "OUTBOX_DISPATCH_FAILED:",
        ),
        "outbox dispatcher bounded health log",
    )
    require(
        "str(exc)" not in cli and "repr(exc)" not in cli,
        "outbox dispatcher health log must not serialize exception details",
    )
    log_start = cli.find("        print(\n            json.dumps(")
    failure_raise = cli.find("        if failures:", log_start)
    require(
        log_start >= 0 and failure_raise > log_start,
        "health snapshot must be emitted before a failed cycle exits",
    )

    require_markers(
        tests,
        (
            "test_job_dispatch_health_reads_only_oldest_pending_row",
            'assert "COUNT(" not in query.upper()',
            "test_job_dispatch_health_is_zero_when_queue_is_empty",
            "test_dispatch_cli_emits_bounded_json_health_before_failure",
            'assert "password" not in raw',
            '"oldest_unpublished_age_seconds": 601',
            '"oldest_publish_attempts": 6',
            '"failure_channels": ["jobs"]',
        ),
        "outbox observability executable tests",
    )

    for app, environment, expected_count in (
        (staging_app, "staging", "1"),
        (production_app, "production", "2"),
    ):
        dispatcher = service_block(app, "outbox-dispatcher")
        require_markers(
            dispatcher,
            (
                '"dispatch-outbox"',
                '"--watch"',
                '"--interval"',
                f"desired_count       = {expected_count}",
                "autoscaling_enabled = false",
            ),
            f"{environment} outbox dispatcher service",
        )

    validate_environment_iac(staging_iac, environment="staging")
    validate_environment_iac(production_iac, environment="production")

    for workflow, label in (
        (video_workflow, "Video Generation workflow"),
        (production_iac_workflow, "Production IaC workflow"),
        (final_workflow, "Final Acceptance workflow"),
    ):
        require(
            f"python3 {SELF_PATH}" in workflow,
            f"{label} does not execute outbox observability contract",
        )
        require(
            f"{SELF_PATH} \\" in workflow,
            f"{label} does not syntax-gate outbox observability contract",
        )

    print("Outbox dispatcher operational observability contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OutboxObservabilityContractError as exc:
        raise SystemExit(f"Outbox observability contract failed: {exc}") from exc
