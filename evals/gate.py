from __future__ import annotations

from typing import Any

from .models import SuiteDefinition


class GateError(RuntimeError):
    """Raised when baseline/candidate results cannot be compared safely."""


def _score(run: dict[str, Any], metric: str) -> float:
    scores = run.get("scores")
    if not isinstance(scores, dict) or metric not in scores:
        raise GateError(f"run {run.get('run_id', '<unknown>')} missing score {metric}")
    value = scores[metric]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise GateError(f"score {metric} must be numeric")
    return float(value)


def compare_runs(
    suite: SuiteDefinition,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if baseline.get("suite") != candidate.get("suite") or baseline.get("suite") != suite.name:
        raise GateError("baseline and candidate must target the same suite")
    if baseline.get("suite_version") != candidate.get("suite_version"):
        raise GateError("baseline and candidate suite versions must match")

    checks: list[dict[str, Any]] = []
    primary = suite.gate.get("primary")
    if not isinstance(primary, dict):
        raise GateError("suite.gate.primary must be an object")
    primary_metric = primary.get("metric", suite.primary_metric)
    max_regression = float(primary.get("max_regression", 0.0))
    baseline_primary = _score(baseline, primary_metric)
    candidate_primary = _score(candidate, primary_metric)
    primary_passed = candidate_primary >= baseline_primary - max_regression
    checks.append(
        {
            "name": "primary_metric",
            "metric": primary_metric,
            "baseline": baseline_primary,
            "candidate": candidate_primary,
            "rule": f"candidate >= baseline - {max_regression}",
            "passed": primary_passed,
        }
    )

    guardrails = suite.gate.get("guardrails", [])
    if not isinstance(guardrails, list):
        raise GateError("suite.gate.guardrails must be an array")
    for guardrail in guardrails:
        if not isinstance(guardrail, dict):
            raise GateError("each guardrail must be an object")
        metric = guardrail.get("metric")
        comparison = guardrail.get("comparison")
        if not isinstance(metric, str) or not metric:
            raise GateError("guardrail.metric must be a non-empty string")
        baseline_value = _score(baseline, metric)
        candidate_value = _score(candidate, metric)
        if comparison == "not_increase":
            passed = candidate_value <= baseline_value
            rule = "candidate <= baseline"
        elif comparison == "max_ratio":
            max_ratio = float(guardrail.get("value", 1.0))
            if baseline_value == 0:
                passed = candidate_value == 0
            else:
                passed = candidate_value <= baseline_value * max_ratio
            rule = f"candidate <= baseline * {max_ratio}"
        elif comparison == "max_absolute":
            limit = float(guardrail.get("value", 0.0))
            passed = candidate_value <= limit
            rule = f"candidate <= {limit}"
        elif comparison == "min_absolute":
            limit = float(guardrail.get("value", 0.0))
            passed = candidate_value >= limit
            rule = f"candidate >= {limit}"
        else:
            raise GateError(f"unsupported guardrail comparison: {comparison}")
        checks.append(
            {
                "name": "guardrail",
                "metric": metric,
                "baseline": baseline_value,
                "candidate": candidate_value,
                "rule": rule,
                "passed": passed,
            }
        )

    return {
        "schema_version": 1,
        "suite": suite.name,
        "suite_version": suite.version,
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
