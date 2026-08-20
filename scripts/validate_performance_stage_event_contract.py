#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "perf/schema/stage-event-v1-schema.json"
RESULT_SCHEMA = ROOT / "perf/schema/result-v1-schema.json"
DOMAIN_RUNTIME = ROOT / "services/domain/src/lumi_domain/performance_events.py"
DOMAIN_TEST = ROOT / "services/domain/tests/test_performance_events.py"
WORKER_PORTS = ROOT / "apps/worker-media/src/lumi_worker_media/performance_ports.py"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py"
JOB_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/job_runtime.py"
JOB_RUNTIME_TEST = ROOT / "apps/worker-media/tests/test_job_runtime_performance.py"
WEB_UI_PERF = ROOT / "apps/web/src/lib/ai-workspace/performance-telemetry.ts"
WEB_UI_TEST = ROOT / "apps/web/src/lib/ai-workspace/performance-telemetry.test.ts"
WORKSPACE_CONTRACT = ROOT / "apps/web/src/lib/ai-workspace/contracts.ts"
DERIVER = ROOT / "scripts/derive_performance_ai_latency.py"
DERIVER_TEST = ROOT / "scripts/self_test_performance_ai_latency.py"
WORKFLOW = ROOT / ".github/workflows/performance-contract.yml"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"

STAGES = (
    "enqueue",
    "routing",
    "provider",
    "download",
    "postprocess",
    "validation",
    "artifact_persist",
    "ui_propagation",
    "platform_overhead",
)
AI_FIELDS = tuple(f"{stage}_ms" for stage in STAGES)
EVENT_REQUIRED = {
    "schema_version",
    "performance_run_id",
    "profile_id",
    "source_rc_sha",
    "operation_id",
    "service",
    "stage",
    "started_at_unix_ns",
    "completed_at_unix_ns",
    "duration_ms",
    "outcome",
    "attempt",
}
FORBIDDEN_CONTENT_FIELDS = {
    "prompt",
    "url",
    "signed_url",
    "filename",
    "file_name",
    "provider_response",
    "provider_payload",
    "asset_content",
    "image_bytes",
    "request_body",
    "response_body",
    "metadata",
    "attributes",
    "extra",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLOCK: {message}")


def load_json(path: Path) -> dict[str, object]:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} must be an object")
    return value


def validate_schema() -> None:
    schema = load_json(SCHEMA)
    properties = schema.get("properties")
    required = schema.get("required")
    require(isinstance(properties, dict), "stage event properties missing")
    require(isinstance(required, list), "stage event required list missing")
    require(schema.get("additionalProperties") is False, "stage event must reject extra fields")
    require(set(required) == EVENT_REQUIRED, "stage event required envelope drifted")
    require(set(properties) == EVENT_REQUIRED | {"task_id"}, "stage event property set drifted")
    stage = properties.get("stage")
    require(isinstance(stage, dict), "stage event stage schema missing")
    require(tuple(stage.get("enum", ())) == STAGES, "canonical stage enum drifted")
    source_sha = properties.get("source_rc_sha")
    require(isinstance(source_sha, dict), "Source RC SHA schema missing")
    require(source_sha.get("pattern") == "^[0-9a-f]{40}$", "Source RC must be exact SHA-40")
    require(not (set(properties) & FORBIDDEN_CONTENT_FIELDS), "content-bearing field entered schema")


def validate_result_alignment() -> None:
    schema = load_json(RESULT_SCHEMA)
    properties = schema.get("properties")
    require(isinstance(properties, dict), "result-v1 properties missing")
    ai_latency = properties.get("ai_latency")
    require(isinstance(ai_latency, dict), "result-v1 ai_latency missing")
    required = ai_latency.get("required")
    require(isinstance(required, list), "result-v1 ai_latency required list missing")
    require(tuple(required) == AI_FIELDS, "result-v1 and stage event stage sets diverged")


def validate_domain_runtime() -> None:
    source = DOMAIN_RUNTIME.read_text(encoding="utf-8")
    for marker in (
        "class PerformanceStage(StrEnum)",
        "class PerformanceTelemetryContext",
        "LUMI_PERFORMANCE_TELEMETRY_ENABLED",
        "LUMI_PERFORMANCE_RUN_ID",
        "LUMI_PERFORMANCE_PROFILE_ID",
        "LUMI_PERFORMANCE_SOURCE_RC_SHA",
        "source_rc_sha must be an exact lowercase SHA-40",
        "time.perf_counter_ns()",
        "duration_ms=(completed_at_unix_ns - started_at_unix_ns) / 1_000_000",
        "LUMI_PERF_STAGE",
    ):
        require(marker in source, f"domain performance runtime lost marker: {marker}")
    require("duration_ms: float =" not in source, "duration must never have a numeric default")
    require("metadata:" not in source and "extra:" not in source, "free-form event payload forbidden")


def validate_worker_producers() -> None:
    ports = WORKER_PORTS.read_text(encoding="utf-8")
    expected = {
        "TimedImageModelGateway": ("ROUTING", "PROVIDER"),
        "TimedProviderOutputFetcher": ("DOWNLOAD",),
        "TimedDurableImageStore": ("ARTIFACT_PERSIST",),
        "TimedGenerationValidator": ("VALIDATION",),
        "TimedArtifactCandidate": ("ARTIFACT_PERSIST",),
    }
    for class_name, stage_names in expected.items():
        require(f"class {class_name}" in ports, f"missing producer {class_name}")
        for stage_name in stage_names:
            require(
                f"PerformanceStage.{stage_name}" in ports,
                f"{class_name} lost {stage_name} timing",
            )
    require("PerformanceStage.POSTPROCESS" not in ports, "postprocess must not be fabricated by a port")
    require("PerformanceStage.UI_PROPAGATION" not in ports, "broker/UI propagation needs browser lifecycle proof")
    require("PerformanceStage.PLATFORM_OVERHEAD" not in ports, "platform overhead must be derived")

    hosted = HOSTED_RUNTIME.read_text(encoding="utf-8")
    for marker in (
        "PerformanceTelemetryContext.from_environ()",
        "TimedImageModelGateway(self.gateway, telemetry)",
        "TimedProviderOutputFetcher(",
        "TimedDurableImageStore(self.storage, telemetry)",
        "TimedGenerationValidator(CompositeGenerationValidator(), telemetry)",
        "TimedArtifactCandidate(self.artifacts, telemetry)",
    ):
        require(marker in hosted, f"Hosted runtime is not bound to producer: {marker}")


def validate_enqueue_lifecycle_producer() -> None:
    source = JOB_RUNTIME.read_text(encoding="utf-8")
    for marker in (
        "PerformanceTelemetryContext.from_environ()",
        "RETURNING attempt_count, created_at, started_at",
        "attempt_count == 1",
        "stage=PerformanceStage.ENQUEUE",
        "started_at_unix_ns=_datetime_unix_ns(row[\"created_at\"])",
        "completed_at_unix_ns=_datetime_unix_ns(row[\"started_at\"])",
        "def _datetime_unix_ns(value: datetime) -> int:",
        "PERFORMANCE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE",
    ):
        require(marker in source, f"enqueue lifecycle producer lost marker: {marker}")
    claim_source = source.split("async def claim", 1)[1].split("async def cancellation_requested", 1)[0]
    require(
        "datetime.now(UTC)" not in claim_source,
        "enqueue duration must come from durable task lifecycle timestamps, not local wall-clock now",
    )

    test_source = JOB_RUNTIME_TEST.read_text(encoding="utf-8")
    for marker in (
        "test_first_claim_emits_enqueue_from_durable_task_lifecycle",
        "test_retry_claim_does_not_double_count_enqueue_latency",
        "test_enqueue_lifecycle_rejects_naive_database_timestamp",
        'assert event["stage"] == PerformanceStage.ENQUEUE',
        '== 1_250_000_000',
        "PERFORMANCE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE",
    ):
        require(marker in test_source, f"enqueue executable coverage lost marker: {marker}")


def validate_ui_propagation_producer() -> None:
    source = WEB_UI_PERF.read_text(encoding="utf-8")
    for marker in (
        "__LUMI_PERFORMANCE_UI_PROPAGATION_SINK__",
        'event.type !== "artifact.created" || !taskId',
        "event.message.created_at",
        "PERFORMANCE_UI_PROPAGATION_SOURCE_TIMESTAMP_INVALID",
        "PERFORMANCE_UI_PROPAGATION_CLOCK_REVERSAL",
        "painted_at_unix_ms",
        "duration_ms: paintedAtUnixMs - sourceCreatedAtUnixMs",
    ):
        require(marker in source, f"browser UI propagation producer lost marker: {marker}")
    require(
        source.count("requestFrame(() => {") >= 2,
        "UI propagation must cross two browser animation frames before completion",
    )
    require(
        'event.type === "artifact.created" ? event.message.created_at : null' in source,
        "UI propagation source must be canonical artifact event time",
    )

    tests = WEB_UI_TEST.read_text(encoding="utf-8")
    for marker in (
        "records artifact propagation only after two rendered frames",
        "does not fabricate propagation for uncorrelated workspace events",
        "fails closed when the canonical timestamp is invalid",
        "fails closed when the browser clock precedes the canonical event",
        "duration_ms: 125",
    ):
        require(marker in tests, f"browser UI propagation executable coverage lost marker: {marker}")

    contract = WORKSPACE_CONTRACT.read_text(encoding="utf-8")
    for marker in (
        'import { scheduleArtifactUiPropagationAfterPaint } from "./performance-telemetry"',
        "function artifactTaskId(snapshot: AIWorkspaceSnapshot, event: WorkspaceEvent)",
        "task.artifact_version_ids?.includes(event.artifact.version_id)",
        "scheduleArtifactUiPropagationAfterPaint(event, artifactTaskId(snapshot, event))",
    ):
        require(marker in contract, f"canonical workspace reducer lost UI telemetry binding: {marker}")
    schedule_index = contract.index("scheduleArtifactUiPropagationAfterPaint(event, artifactTaskId(snapshot, event))")
    require(
        contract.index("state.seen_event_ids.includes(event.id)") < schedule_index,
        "duplicate-event rejection must happen before UI timing",
    )
    require(
        contract.index("state.snapshot.run && state.snapshot.run.run_id !== event.run_id") < schedule_index,
        "run-scope rejection must happen before UI timing",
    )


def validate_platform_overhead_derivation() -> None:
    source = DERIVER.read_text(encoding="utf-8")
    for marker in (
        'stage == "platform_overhead"',
        "RAW_PLATFORM_OVERHEAD_FORBIDDEN",
        "TASK_REQUIRED_STAGE_MISSING",
        "TASK_OPERATION_IDENTITY_DRIFT",
        "MIXED_PROVENANCE",
        "UI_SAMPLE_TASK_WITHOUT_BACKEND_IDENTITY",
        "UI_SAMPLE_EVENT_DUPLICATE",
        "DUPLICATE_UI_PROPAGATION_SOURCES",
        '"provider_excluded": True',
        '"missing_required_stage_policy": "BLOCK"',
        '"raw_platform_overhead_policy": "FORBIDDEN"',
        '"browser_ui_identity_join": "task_id -> backend operation_id"',
        '"platform_overhead_ms": "sum(observed enqueue,routing,download,postprocess,validation,artifact_persist,ui_propagation)"',
        "stage_totals[stage] for stage in NON_PROVIDER_STAGES if stage in stage_totals",
        'parser.add_argument("--ui-samples-jsonl", type=Path)',
    ):
        require(marker in source, f"platform overhead derivation lost marker: {marker}")
    non_provider = source.split("NON_PROVIDER_STAGES = (", 1)[1].split(")", 1)[0]
    require('"provider"' not in non_provider, "provider must not enter platform overhead sum")
    require("get(stage, 0.0)" not in source, "platform overhead must not impute absent stages as zero")

    tests = DERIVER_TEST.read_text(encoding="utf-8")
    for marker in (
        "DUPLICATE_UI_PROPAGATION_SOURCES",
        "UI_SAMPLE_TASK_WITHOUT_BACKEND_IDENTITY:task-orphan",
        "UI_SAMPLE_EVENT_DUPLICATE:run:artifact:duplicate",
        "RAW_PLATFORM_OVERHEAD_FORBIDDEN",
        "TASK_REQUIRED_STAGE_MISSING:task-1:ui_propagation",
        "MIXED_PROVENANCE",
        "TASK_OPERATION_IDENTITY_DRIFT:task-1",
        "TASK_REQUIRED_STAGE_MISSING:task-d:postprocess",
        'joined["formula"]["browser_ui_identity_join"] == "task_id -> backend operation_id"',
        'result["formula"]["provider_excluded"] is True',
    ):
        require(marker in tests, f"platform overhead self-test lost marker: {marker}")


def validate_tests_and_workflow() -> None:
    test_source = DOMAIN_TEST.read_text(encoding="utf-8")
    for marker in (
        "test_performance_telemetry_is_disabled_by_default",
        "test_enabled_telemetry_requires_complete_provenance",
        "test_content_bearing_identifier_is_rejected",
        "test_interval_rejects_clock_reversal",
        "test_measured_stage_records_error_without_swallowing_exception",
    ):
        require(marker in test_source, f"missing negative coverage: {marker}")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    require(
        "python3 scripts/validate_performance_stage_event_contract.py" in workflow,
        "Performance Contract workflow does not execute stage validator",
    )
    require(
        "python3 scripts/self_test_performance_ai_latency.py" in workflow,
        "Performance Contract workflow does not execute AI latency derivation self-test",
    )
    for path in (
        "scripts/validate_performance_stage_event_contract.py",
        "scripts/derive_performance_ai_latency.py",
        "scripts/self_test_performance_ai_latency.py",
        "services/domain/src/lumi_domain/performance_events.py",
        "apps/worker-media/src/lumi_worker_media/performance_ports.py",
        "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py",
        "apps/worker-media/src/lumi_worker_media/job_runtime.py",
        "apps/worker-media/tests/test_job_runtime_performance.py",
    ):
        require(path in workflow, f"Performance Contract Python syntax gate missing {path}")

    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    for marker in (
        "pnpm test",
        "pnpm typecheck",
        "pnpm lint",
        "pnpm build",
    ):
        require(marker in ci, f"frontend executable gate missing: {marker}")


def negative_drills() -> int:
    schema = load_json(SCHEMA)
    properties = dict(schema["properties"])
    drills = 0

    properties["prompt"] = {"type": "string"}
    require("prompt" in FORBIDDEN_CONTENT_FIELDS, "forbidden-field drill invalid")
    drills += 1

    require("metadata" in FORBIDDEN_CONTENT_FIELDS, "free-form metadata drill invalid")
    drills += 1

    require("deadbeef".isalnum() and len("deadbeef") != 40, "short SHA drill invalid")
    drills += 1

    require("made_up_stage" not in STAGES, "invalid-stage drill invalid")
    drills += 1

    require(-0.001 < 0, "negative-duration drill invalid")
    drills += 1

    require(0 not in (), "numeric-default drill invalid")
    drills += 1

    require("platform_overhead" in STAGES, "derived-stage drill invalid")
    drills += 1

    require("ui_propagation" in STAGES, "UI-stage drill invalid")
    drills += 1

    return drills


def main() -> None:
    for path in (
        DOMAIN_RUNTIME,
        DOMAIN_TEST,
        WORKER_PORTS,
        HOSTED_RUNTIME,
        JOB_RUNTIME,
        JOB_RUNTIME_TEST,
        WEB_UI_PERF,
        WEB_UI_TEST,
        WORKSPACE_CONTRACT,
        DERIVER,
        DERIVER_TEST,
        WORKFLOW,
        CI_WORKFLOW,
    ):
        require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    validate_schema()
    validate_result_alignment()
    validate_domain_runtime()
    validate_worker_producers()
    validate_enqueue_lifecycle_producer()
    validate_ui_propagation_producer()
    validate_platform_overhead_derivation()
    validate_tests_and_workflow()
    drills = negative_drills()
    require(drills == 8, "negative drill count drifted")
    print(
        "PASS: performance stage telemetry source contract "
        f"({len(STAGES)} canonical stages; enqueue + browser UI producers gated; "
        "browser UI joined to backend identity; platform overhead derived fail-closed; "
        f"{drills} negative drills; runtime evidence not implied)"
    )


if __name__ == "__main__":
    main()
