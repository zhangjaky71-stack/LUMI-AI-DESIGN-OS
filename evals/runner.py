from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .graders import grade_case
from .models import CandidateProfile, EvalCase, MetricDefinition, SchemaError, SuiteDefinition


class EvaluationError(RuntimeError):
    """Raised when an evaluation run cannot be completed."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot load JSON file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SchemaError(f"top-level JSON in {path} must be an object")
    return raw


def load_suite(root: Path, suite_name: str) -> tuple[SuiteDefinition, list[EvalCase]]:
    suite_root = root / "datasets" / suite_name
    manifest = SuiteDefinition.from_dict(load_json(suite_root / "suite.json"))
    cases_payload = load_json(suite_root / "v1" / "cases.json")
    cases_raw = cases_payload.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise SchemaError("dataset cases must be a non-empty array")
    cases = [EvalCase.from_dict(case) for case in cases_raw]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise SchemaError("dataset case ids must be unique")
    if any(case.suite != manifest.name for case in cases):
        raise SchemaError("every case.suite must match suite.name")
    return manifest, cases


def load_candidate(path: Path) -> CandidateProfile:
    return CandidateProfile.from_dict(load_json(path))


def _git_sha() -> str:
    github_sha = os.getenv("GITHUB_SHA")
    if github_sha:
        return github_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _p95(values: list[float]) -> float:
    if not values:
        raise EvaluationError("cannot aggregate empty metric")
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


def aggregate(values: list[float], definition: MetricDefinition) -> float:
    if not values:
        raise EvaluationError("cannot aggregate empty metric")
    if definition.aggregation == "mean":
        return sum(values) / len(values)
    if definition.aggregation == "sum":
        return sum(values)
    if definition.aggregation == "min":
        return min(values)
    if definition.aggregation == "max":
        return max(values)
    if definition.aggregation == "p95":
        return _p95(values)
    raise EvaluationError(f"unsupported aggregation: {definition.aggregation}")


def run_suite(
    eval_root: Path,
    suite_name: str,
    candidate_path: Path,
    *,
    git_sha: str | None = None,
) -> dict[str, Any]:
    suite, cases = load_suite(eval_root, suite_name)
    candidate = load_candidate(candidate_path)
    metric_values: dict[str, list[float]] = {name: [] for name in suite.metrics}
    case_results: list[dict[str, Any]] = []
    trace_ids: list[str] = []

    for case in cases:
        response = candidate.responses.get(case.id)
        if response is None:
            raise EvaluationError(f"candidate {candidate.name}@{candidate.version} missing case {case.id}")
        scores = grade_case(case, response.output)
        scores["cost_usd"] = response.cost_usd
        scores["latency_ms"] = response.duration_ms
        for metric, score in scores.items():
            if metric not in metric_values:
                raise EvaluationError(f"metric {metric} is not declared by suite {suite.name}")
            metric_values[metric].append(score)
        trace_ids.extend(response.trace_ids)
        case_results.append(
            {
                "case_id": case.id,
                "case_version": case.version,
                "scores": scores,
                "trace_ids": list(response.trace_ids),
            }
        )

    aggregated = {
        metric: aggregate(values, suite.metrics[metric])
        for metric, values in metric_values.items()
        if values
    }
    resolved_git_sha = git_sha or _git_sha()
    run_identity = {
        "suite": suite.name,
        "suite_version": suite.version,
        "candidate": {"name": candidate.name, "version": candidate.version},
        "git_sha": resolved_git_sha,
        "scores": aggregated,
        "cases": case_results,
    }
    run_id = hashlib.sha256(
        json.dumps(run_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "suite": suite.name,
        "suite_version": suite.version,
        "primary_metric": suite.primary_metric,
        "candidate": {
            "name": candidate.name,
            "version": candidate.version,
            "metadata": candidate.metadata,
        },
        "scores": aggregated,
        "trace_ids": sorted(set(trace_ids)),
        "git_sha": resolved_git_sha,
        "cases": case_results,
        "metric_definitions": {
            name: asdict(definition) for name, definition in suite.metrics.items()
        },
    }
