#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "perf" / "profiles" / "v1"

MEASURE_TO_STAGE = {
    "enqueue_p50_ms": "enqueue",
    "enqueue_p95_ms": "enqueue",
    "queue_wait_ms": "enqueue",
    "routing_ms": "routing",
    "provider_latency_ms": "provider",
    "download_ms": "download",
    "postprocess_ms": "postprocess",
    "validation_ms": "validation",
    "artifact_persist_ms": "artifact_persist",
    "sse_platform_propagation_ms": "ui_propagation",
}
NON_PROVIDER_STAGES = (
    "enqueue",
    "routing",
    "download",
    "postprocess",
    "validation",
    "artifact_persist",
    "ui_propagation",
)
CANONICAL_STAGES = frozenset((*NON_PROVIDER_STAGES, "provider", "platform_overhead"))
REQUIRED_EVENT_FIELDS = frozenset(
    {
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
)


def block(message: str) -> None:
    raise ValueError(f"PERFORMANCE_AI_LATENCY_BLOCK:{message}")


def _number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        block(f"{name}_MUST_BE_NUMERIC")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        block(f"{name}_MUST_BE_FINITE_NONNEGATIVE")
    return result


def load_profile(profile_id: str) -> dict[str, Any]:
    matches = list(PROFILES.glob(f"{profile_id}-*.json"))
    if len(matches) != 1:
        block(f"PROFILE_{profile_id}_NOT_UNIQUE")
    value = json.loads(matches[0].read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("id") != profile_id:
        block("PROFILE_ID_MISMATCH")
    return value


def required_stages(profile: dict[str, Any]) -> tuple[str, ...]:
    measures = profile.get("measure")
    if not isinstance(measures, list) or not all(isinstance(value, str) for value in measures):
        block("PROFILE_MEASURE_INVALID")
    stages: list[str] = []
    for measure in measures:
        stage = MEASURE_TO_STAGE.get(measure)
        if stage is not None and stage not in stages:
            stages.append(stage)
    return tuple(stages)


def validate_event(event: object) -> dict[str, Any]:
    if not isinstance(event, dict):
        block("EVENT_OBJECT_REQUIRED")
    missing = REQUIRED_EVENT_FIELDS - set(event)
    if missing:
        block(f"EVENT_FIELDS_MISSING:{','.join(sorted(missing))}")
    if event.get("schema_version") != 1:
        block("EVENT_SCHEMA_VERSION")
    stage = event.get("stage")
    if stage not in CANONICAL_STAGES:
        block("EVENT_STAGE_INVALID")
    if stage == "platform_overhead":
        block("RAW_PLATFORM_OVERHEAD_FORBIDDEN")
    task_id = event.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        block("TASK_ID_REQUIRED_FOR_AI_LATENCY")
    for field in ("performance_run_id", "profile_id", "source_rc_sha", "operation_id", "service"):
        if not isinstance(event.get(field), str) or not event[field]:
            block(f"EVENT_{field.upper()}_INVALID")
    if event.get("outcome") not in {"success", "error"}:
        block("EVENT_OUTCOME_INVALID")
    attempt = event.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        block("EVENT_ATTEMPT_INVALID")
    started = event.get("started_at_unix_ns")
    completed = event.get("completed_at_unix_ns")
    if isinstance(started, bool) or not isinstance(started, int) or started < 0:
        block("EVENT_START_INVALID")
    if isinstance(completed, bool) or not isinstance(completed, int) or completed < started:
        block("EVENT_END_INVALID")
    duration = _number(event.get("duration_ms"), name="EVENT_DURATION")
    expected = (completed - started) / 1_000_000
    if not math.isclose(duration, expected, rel_tol=0.0, abs_tol=0.001):
        block("EVENT_DURATION_TIMESTAMP_MISMATCH")
    return event


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        block("PERCENTILE_EMPTY")
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def derive(events: list[object], *, profile_id: str) -> dict[str, Any]:
    profile = load_profile(profile_id)
    required = required_stages(profile)
    if not required:
        block(f"PROFILE_{profile_id}_HAS_NO_AI_STAGE_REQUIREMENTS")

    validated = [validate_event(value) for value in events]
    if not validated:
        block("NO_STAGE_EVENTS")

    provenance = {
        (
            event["performance_run_id"],
            event["profile_id"],
            event["source_rc_sha"],
        )
        for event in validated
    }
    if len(provenance) != 1:
        block("MIXED_PROVENANCE")
    performance_run_id, observed_profile_id, source_rc_sha = next(iter(provenance))
    if observed_profile_id != profile_id:
        block("REQUESTED_PROFILE_DOES_NOT_MATCH_EVENTS")

    by_task: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    operation_by_task: dict[str, str] = {}
    outcome_by_task: dict[str, set[str]] = defaultdict(set)
    for event in validated:
        task_id = event["task_id"]
        operation_id = event["operation_id"]
        prior_operation = operation_by_task.setdefault(task_id, operation_id)
        if prior_operation != operation_id:
            block(f"TASK_OPERATION_IDENTITY_DRIFT:{task_id}")
        by_task[task_id][event["stage"]] += float(event["duration_ms"])
        outcome_by_task[task_id].add(event["outcome"])

    task_rows: list[dict[str, Any]] = []
    for task_id in sorted(by_task):
        stage_totals = by_task[task_id]
        missing = [stage for stage in required if stage not in stage_totals]
        if missing:
            block(f"TASK_REQUIRED_STAGE_MISSING:{task_id}:{','.join(missing)}")
        if "error" in outcome_by_task[task_id]:
            block(f"TASK_STAGE_ERROR_PRESENT:{task_id}")
        platform_overhead = sum(stage_totals.get(stage, 0.0) for stage in NON_PROVIDER_STAGES)
        task_rows.append(
            {
                "task_id": task_id,
                "operation_id": operation_by_task[task_id],
                "stage_totals_ms": {stage: stage_totals[stage] for stage in sorted(stage_totals)},
                "platform_overhead_ms": platform_overhead,
            }
        )

    stage_summary: dict[str, dict[str, float | int]] = {}
    for stage in required:
        values = [row["stage_totals_ms"][stage] for row in task_rows]
        stage_summary[stage] = {
            "samples": len(values),
            "p50_ms": percentile(values, 0.50),
            "p95_ms": percentile(values, 0.95),
        }

    overhead_values = [float(row["platform_overhead_ms"]) for row in task_rows]
    provider_values = [
        float(row["stage_totals_ms"]["provider"])
        for row in task_rows
        if "provider" in row["stage_totals_ms"]
    ]
    return {
        "schema_version": 1,
        "kind": "lumi_ai_latency_derived_v1",
        "performance_run_id": performance_run_id,
        "profile_id": profile_id,
        "source_rc_sha": source_rc_sha,
        "task_count": len(task_rows),
        "required_raw_stages": list(required),
        "formula": {
            "platform_overhead_ms": "sum(enqueue,routing,download,postprocess,validation,artifact_persist,ui_propagation)",
            "provider_excluded": True,
            "missing_required_stage_policy": "BLOCK",
            "raw_platform_overhead_policy": "FORBIDDEN",
        },
        "stage_summary": stage_summary,
        "provider_summary": (
            {
                "samples": len(provider_values),
                "p50_ms": percentile(provider_values, 0.50),
                "p95_ms": percentile(provider_values, 0.95),
            }
            if provider_values
            else None
        ),
        "platform_overhead_summary": {
            "samples": len(overhead_values),
            "p50_ms": percentile(overhead_values, 0.50),
            "p95_ms": percentile(overhead_values, 0.95),
        },
        "tasks": task_rows,
    }


def read_jsonl(path: Path) -> list[object]:
    values: list[object] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            values.append(json.loads(text))
        except json.JSONDecodeError as exc:
            block(f"JSONL_INVALID_LINE_{line_number}:{exc.msg}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("events_jsonl", type=Path)
    parser.add_argument("--profile-id", required=True, choices=list("ABCDEFG"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = derive(read_jsonl(args.events_jsonl), profile_id=args.profile_id)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
