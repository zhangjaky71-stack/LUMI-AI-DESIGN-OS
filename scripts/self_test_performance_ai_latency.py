#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from derive_performance_ai_latency import derive

SHA = "a" * 40
RUN_ID = "node69-ai-latency-selftest"
SOURCE_ISO = "2026-08-20T10:00:00.000Z"
SOURCE_MS = int(datetime(2026, 8, 20, 10, 0, tzinfo=UTC).timestamp() * 1000)


def event(
    *,
    task: str,
    operation: str,
    stage: str,
    duration_ms: float,
    profile: str = "C",
    start_ns: int = 1_000_000_000,
) -> dict[str, object]:
    duration_ns = int(duration_ms * 1_000_000)
    return {
        "schema_version": 1,
        "performance_run_id": RUN_ID,
        "profile_id": profile,
        "source_rc_sha": SHA,
        "operation_id": operation,
        "task_id": task,
        "service": "selftest",
        "stage": stage,
        "started_at_unix_ns": start_ns,
        "completed_at_unix_ns": start_ns + duration_ns,
        "duration_ms": duration_ms,
        "outcome": "success",
        "attempt": 1,
    }


def ui_sample(*, task: str, event_id: str, duration_ms: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "run_id": "agent-run-selftest",
        "task_id": task,
        "event_type": "artifact.created",
        "source_created_at": SOURCE_ISO,
        "source_created_at_unix_ms": SOURCE_MS,
        "painted_at_unix_ms": SOURCE_MS + duration_ms,
        "duration_ms": duration_ms,
    }


def c_events() -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for task, operation, base in (("task-1", "op-1", 10.0), ("task-2", "op-2", 20.0)):
        values.extend(
            [
                event(task=task, operation=operation, stage="enqueue", duration_ms=base),
                event(task=task, operation=operation, stage="routing", duration_ms=base + 1),
                event(task=task, operation=operation, stage="provider", duration_ms=base + 100),
                event(task=task, operation=operation, stage="ui_propagation", duration_ms=base + 2),
            ]
        )
    return values


def expect_block(
    events: list[dict[str, object]],
    profile: str,
    marker: str,
    *,
    ui_samples: list[dict[str, object]] | None = None,
) -> None:
    try:
        derive(events, profile_id=profile, ui_samples=ui_samples)
    except ValueError as exc:
        if marker not in str(exc):
            raise AssertionError(f"expected {marker}, got {exc}") from exc
    else:
        raise AssertionError(f"expected BLOCK containing {marker}")


def main() -> int:
    values = c_events()
    result = derive(values, profile_id="C")
    assert result["task_count"] == 2
    assert result["required_raw_stages"] == ["enqueue", "routing", "provider", "ui_propagation"]
    tasks = {row["task_id"]: row for row in result["tasks"]}
    assert tasks["task-1"]["platform_overhead_ms"] == 10.0 + 11.0 + 12.0
    assert tasks["task-2"]["platform_overhead_ms"] == 20.0 + 21.0 + 22.0
    assert tasks["task-1"]["stage_totals_ms"]["provider"] == 110.0
    assert result["platform_overhead_summary"]["p95_ms"] == 63.0
    assert result["provider_summary"]["p95_ms"] == 120.0
    assert result["formula"]["provider_excluded"] is True
    assert result["formula"]["missing_required_stage_policy"] == "BLOCK"

    backend_without_ui = [value for value in values if value["stage"] != "ui_propagation"]
    browser_samples = [
        ui_sample(task="task-1", event_id="run:artifact:1", duration_ms=12),
        ui_sample(task="task-2", event_id="run:artifact:2", duration_ms=22),
    ]
    joined = derive(backend_without_ui, profile_id="C", ui_samples=browser_samples)
    joined_tasks = {row["task_id"]: row for row in joined["tasks"]}
    assert joined["ui_sample_count"] == 2
    assert joined_tasks["task-1"]["operation_id"] == "op-1"
    assert joined_tasks["task-1"]["stage_totals_ms"]["ui_propagation"] == 12.0
    assert joined_tasks["task-1"]["platform_overhead_ms"] == 33.0
    assert joined["formula"]["browser_ui_identity_join"] == "task_id -> backend operation_id"

    expect_block(
        values,
        "C",
        "DUPLICATE_UI_PROPAGATION_SOURCES",
        ui_samples=browser_samples,
    )
    expect_block(
        backend_without_ui,
        "C",
        "UI_SAMPLE_TASK_WITHOUT_BACKEND_IDENTITY:task-orphan",
        ui_samples=[ui_sample(task="task-orphan", event_id="run:artifact:orphan", duration_ms=9)],
    )
    expect_block(
        backend_without_ui,
        "C",
        "UI_SAMPLE_EVENT_DUPLICATE:run:artifact:duplicate",
        ui_samples=[
            ui_sample(task="task-1", event_id="run:artifact:duplicate", duration_ms=12),
            ui_sample(task="task-2", event_id="run:artifact:duplicate", duration_ms=22),
        ],
    )

    raw_overhead = deepcopy(values)
    raw_overhead.append(
        event(task="task-1", operation="op-1", stage="platform_overhead", duration_ms=999.0)
    )
    expect_block(raw_overhead, "C", "RAW_PLATFORM_OVERHEAD_FORBIDDEN")

    missing_ui = [
        value
        for value in values
        if not (value["task_id"] == "task-1" and value["stage"] == "ui_propagation")
    ]
    expect_block(missing_ui, "C", "TASK_REQUIRED_STAGE_MISSING:task-1:ui_propagation")

    mixed_provenance = deepcopy(values)
    mixed_provenance[-1]["source_rc_sha"] = "b" * 40
    expect_block(mixed_provenance, "C", "MIXED_PROVENANCE")

    operation_drift = deepcopy(values)
    operation_drift[1]["operation_id"] = "op-other"
    expect_block(operation_drift, "C", "TASK_OPERATION_IDENTITY_DRIFT:task-1")

    d_missing_postprocess = [
        event(task="task-d", operation="op-d", stage="enqueue", duration_ms=1.0, profile="D"),
        event(task="task-d", operation="op-d", stage="provider", duration_ms=2.0, profile="D"),
        event(task="task-d", operation="op-d", stage="download", duration_ms=3.0, profile="D"),
        event(task="task-d", operation="op-d", stage="validation", duration_ms=4.0, profile="D"),
        event(task="task-d", operation="op-d", stage="artifact_persist", duration_ms=5.0, profile="D"),
        event(task="task-d", operation="op-d", stage="ui_propagation", duration_ms=6.0, profile="D"),
    ]
    expect_block(d_missing_postprocess, "D", "TASK_REQUIRED_STAGE_MISSING:task-d:postprocess")

    print(
        "PASS: AI latency derivation self-test "
        "(browser UI joined by task; provider excluded; raw overhead forbidden; "
        "missing stages/provenance/identity drift block)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
