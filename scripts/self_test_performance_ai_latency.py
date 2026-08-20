#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

from derive_performance_ai_latency import derive

SHA = "a" * 40
RUN_ID = "node69-ai-latency-selftest"


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


def expect_block(events: list[dict[str, object]], profile: str, marker: str) -> None:
    try:
        derive(events, profile_id=profile)
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

    raw_overhead = deepcopy(values)
    raw_overhead.append(
        event(task="task-1", operation="op-1", stage="platform_overhead", duration_ms=999.0)
    )
    expect_block(raw_overhead, "C", "RAW_PLATFORM_OVERHEAD_FORBIDDEN")

    missing_ui = [value for value in values if not (value["task_id"] == "task-1" and value["stage"] == "ui_propagation")]
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
        "(provider excluded; raw overhead forbidden; missing stages/provenance/identity drift block)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
