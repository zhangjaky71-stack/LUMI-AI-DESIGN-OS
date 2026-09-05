#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py"
DOMAIN_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/event_runtime.py"
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


def require_assignment(source: str, key: str, value: str, label: str) -> None:
    pattern = rf"(?m)^\s*{re.escape(key)}\s*=\s*{re.escape(value)}\s*(?:#.*)?$"
    require(
        re.search(pattern, source) is not None,
        f"{label} missing assignment: {key} = {value}",
    )


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


def health_method_block(source: str, *, end_marker: str, label: str) -> str:
    start = source.find("    async def health_snapshot(")
    end = source.find(end_marker, start)
    require(start >= 0 and end > start, f"{label} health query boundary is missing")
    return source[start:end]


def validate_environment_iac(source: str, *, environment: str) -> None:
    require_assignment(
        source,
        "outbox_dispatcher_metric_namespace",
        '"LUMI/MediaDispatch"',
        f"{environment} outbox observability IaC",
    )
    require_markers(
        source,
        (
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
    job_runtime = read(JOB_RUNTIME)
    domain_runtime = read(DOMAIN_RUNTIME)
    cli = read(CLI)
    tests = read(TEST)
    staging_iac = read(STAGING_IAC)
    production_iac = read(PRODUCTION_IAC)
    staging_app = read(STAGING_APP)
    production_app = read(PRODUCTION_APP)
    video_workflow = read(VIDEO_WORKFLOW)
    production_iac_workflow = read(PRODUCTION_IAC_WORKFLOW)
    final_workflow = read(FINAL_WORKFLOW)

    for source, path in (
        (job_runtime, JOB_RUNTIME),
        (domain_runtime, DOMAIN_RUNTIME),
        (cli, CLI),
        (tests, TEST),
    ):
        python_syntax(source, path)

    require_markers(
        job_runtime,
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
    job_health_block = health_method_block(
        job_runtime,
        end_marker="\ndef _validate_media_dispatch",
        label="job dispatcher",
    )
    require(
        "COUNT(" not in job_health_block.upper(),
        "job outbox health must not count/scan the full pending queue every loop",
    )
    require("FOR UPDATE" not in job_health_block.upper(), "job outbox health must remain read-only")

    require_markers(
        domain_runtime,
        (
            "class DomainOutboxHealth",
            "async def health_snapshot(self) -> DomainOutboxHealth:",
            "Read only the oldest pending domain row; never count or lock the full outbox.",
            "EXTRACT(EPOCH FROM (now() - created_at))",
            "publish_attempts AS oldest_publish_attempts",
            "WHERE published_at IS NULL",
            "event_name <> $1",
            "ORDER BY created_at, id",
            "LIMIT 1",
        ),
        "domain dispatcher health query",
    )
    domain_health_block = health_method_block(
        domain_runtime,
        end_marker="\n\nclass EventValidationError",
        label="domain dispatcher",
    )
    require(
        "COUNT(" not in domain_health_block.upper(),
        "domain outbox health must not count/scan the full pending queue every loop",
    )
    require(
        "FOR UPDATE" not in domain_health_block.upper(),
        "domain outbox health must remain read-only",
    )

    domain_dispatch_start = domain_runtime.find("class OutboxDispatcher:")
    domain_dispatch_end = domain_runtime.find("\n\nclass EventValidationError", domain_dispatch_start)
    require(
        domain_dispatch_start >= 0 and domain_dispatch_end > domain_dispatch_start,
        "domain outbox dispatcher boundary missing",
    )
    domain_dispatch_block = domain_runtime[domain_dispatch_start:domain_dispatch_end]
    require_markers(
        domain_dispatch_block,
        (
            "failure: Exception | None = None",
            "publish_attempts + 1",
            "await asyncio.to_thread(self.publisher.publish, record)",
            "failure = exc",
            "if failure is not None:",
            "raise failure",
        ),
        "durable domain publish failure accounting",
    )
    require(
        domain_dispatch_block.find("if failure is not None:")
        > domain_dispatch_block.find("async with connection.transaction():"),
        "domain publish failure must be raised only after transaction exit",
    )

    require_markers(
        cli,
        (
            '_HEALTH_LOG_KIND = "lumi.outbox_dispatcher.health"',
            "job_health = await job_dispatcher.health_snapshot()",
            "domain_health = await domain_dispatcher.health_snapshot()",
            'failures.append(("jobs-health", exc))',
            'failures.append(("domain-health", exc))',
            "oldest_unpublished_age_seconds = max(",
            "oldest_publish_attempts = max(",
            '"oldest_job_unpublished_age_seconds"',
            '"oldest_job_publish_attempts"',
            '"oldest_domain_unpublished_age_seconds"',
            '"oldest_domain_publish_attempts"',
            '"oldest_unpublished_age_seconds": oldest_unpublished_age_seconds',
            '"oldest_publish_attempts": oldest_publish_attempts',
            '"failure_channels": channels',
            '"failure_count": len(failures)',
            '"status": "degraded" if failures else "ok"',
            "json.dumps(",
            "flush=True",
            "OUTBOX_DISPATCH_FAILED:",
        ),
        "outbox dispatcher bounded combined health log",
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
            "test_domain_dispatch_health_reads_only_oldest_pending_row",
            "test_domain_outbox_failed_publish_attempt_commits_before_fail_closed",
            'assert "COUNT(" not in query.upper()',
            'assert "FOR UPDATE" not in query.upper()',
            "assert connection.transaction_state.committed is True",
            "assert connection.transaction_state.exc_type is None",
            "test_job_dispatch_health_is_zero_when_queue_is_empty",
            "test_dispatch_cli_emits_bounded_combined_json_health_before_failure",
            'assert "password" not in raw',
            '"oldest_job_unpublished_age_seconds": 601',
            '"oldest_domain_unpublished_age_seconds": 701',
            '"oldest_unpublished_age_seconds": 701',
            '"oldest_publish_attempts": 9',
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
            ),
            f"{environment} outbox dispatcher service",
        )
        for key in ("desired_count", "min_capacity", "max_capacity"):
            require_assignment(
                dispatcher,
                key,
                expected_count,
                f"{environment} outbox dispatcher static capacity",
            )
        require_assignment(
            dispatcher,
            "autoscaling_enabled",
            "false",
            f"{environment} outbox dispatcher static capacity",
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

    require(
        "apps/worker-media/tests/test_job_dispatch_observability.py" in video_workflow,
        "Video Generation workflow must execute the combined outbox observability regressions",
    )

    print("Outbox dispatcher operational observability contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OutboxObservabilityContractError as exc:
        raise SystemExit(f"Outbox observability contract failed: {exc}") from exc
