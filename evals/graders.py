from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import EvalCase


class GraderError(RuntimeError):
    """Raised when a grader cannot evaluate a case deterministically."""


def _resolve_path(value: Any, path: str) -> Any:
    current = value
    if path == "$":
        return current
    for segment in path.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, list):
            try:
                current = current[int(segment)]
                continue
            except (ValueError, IndexError) as exc:
                raise GraderError(f"path not found: {path}") from exc
        raise GraderError(f"path not found: {path}")
    return current


def _contains_all(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str):
        if isinstance(expected, str):
            return expected in actual
        if isinstance(expected, list):
            return all(isinstance(item, str) and item in actual for item in expected)
    if isinstance(actual, Iterable) and not isinstance(actual, (str, bytes, Mapping)):
        actual_values = list(actual)
        if isinstance(expected, list):
            return all(item in actual_values for item in expected)
    return False


def _matches(actual: Any, op: str, expected: Any) -> bool:
    if op == "equals":
        return actual == expected
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    if op == "contains_all":
        return _contains_all(actual, expected)
    if op == "set_equal":
        if not isinstance(actual, list) or not isinstance(expected, list):
            return False
        try:
            return set(actual) == set(expected)
        except TypeError as exc:
            raise GraderError("set_equal only supports hashable array values") from exc
    if op == "lte":
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and actual <= expected
        )
    if op == "gte":
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and actual >= expected
        )
    if op == "within":
        if not isinstance(expected, Mapping):
            raise GraderError("within expects an object with value and tolerance")
        target = expected.get("value")
        tolerance = expected.get("tolerance")
        if not all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in (actual, target, tolerance)
        ):
            return False
        return abs(float(actual) - float(target)) <= float(tolerance)
    raise GraderError(f"unsupported grader operation: {op}")


def grade_case(case: EvalCase, output: Any) -> dict[str, float]:
    scores: dict[str, float] = {}
    checks = case.grader["checks"]
    for check in checks:
        metric = check["metric"]
        if metric in scores:
            raise GraderError(f"duplicate metric in one case grader: {metric}")
        actual = _resolve_path(output, check["path"])
        expected = check.get("expected")
        passed = _matches(actual, check["op"], expected)
        pass_value = check.get("pass_value", 1.0)
        fail_value = check.get("fail_value", 0.0)
        if not isinstance(pass_value, (int, float)) or isinstance(pass_value, bool):
            raise GraderError(f"pass_value for {metric} must be numeric")
        if not isinstance(fail_value, (int, float)) or isinstance(fail_value, bool):
            raise GraderError(f"fail_value for {metric} must be numeric")
        scores[metric] = float(pass_value if passed else fail_value)
    undeclared = set(scores) - set(case.metrics)
    if undeclared:
        raise GraderError(f"grader produced undeclared metrics: {sorted(undeclared)}")
    missing = set(case.metrics) - set(scores)
    if missing:
        raise GraderError(f"grader did not produce declared metrics: {sorted(missing)}")
    return scores
