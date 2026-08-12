from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SchemaError(ValueError):
    """Raised when benchmark input data does not satisfy the LUMI eval contract."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{field} must be an object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class EvalCase:
    id: str
    suite: str
    version: int
    input: dict[str, Any]
    expected: dict[str, Any]
    metrics: tuple[str, ...]
    grader: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvalCase":
        data = _require_mapping(raw, "case")
        case_id = _require_string(data.get("id"), "case.id")
        suite = _require_string(data.get("suite"), "case.suite")
        version = data.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise SchemaError("case.version must be an integer >= 1")
        input_data = _require_mapping(data.get("input"), "case.input")
        expected = _require_mapping(data.get("expected"), "case.expected")
        grader = _require_mapping(data.get("grader"), "case.grader")
        metrics_raw = data.get("metrics")
        if not isinstance(metrics_raw, list) or not metrics_raw:
            raise SchemaError("case.metrics must be a non-empty array")
        metrics = tuple(_require_string(item, "case.metrics[]") for item in metrics_raw)
        checks = grader.get("checks")
        if not isinstance(checks, list) or not checks:
            raise SchemaError("case.grader.checks must be a non-empty array")
        for index, check in enumerate(checks):
            check_data = _require_mapping(check, f"case.grader.checks[{index}]")
            _require_string(check_data.get("metric"), f"case.grader.checks[{index}].metric")
            _require_string(check_data.get("op"), f"case.grader.checks[{index}].op")
            _require_string(check_data.get("path"), f"case.grader.checks[{index}].path")
        return cls(
            id=case_id,
            suite=suite,
            version=version,
            input=input_data,
            expected=expected,
            metrics=metrics,
            grader=grader,
        )


@dataclass(frozen=True)
class MetricDefinition:
    aggregation: str
    direction: str

    @classmethod
    def from_dict(cls, name: str, raw: Any) -> "MetricDefinition":
        data = _require_mapping(raw, f"metrics.{name}")
        aggregation = _require_string(data.get("aggregation"), f"metrics.{name}.aggregation")
        direction = _require_string(data.get("direction"), f"metrics.{name}.direction")
        if aggregation not in {"mean", "sum", "min", "max", "p95"}:
            raise SchemaError(f"unsupported aggregation for metric {name}: {aggregation}")
        if direction not in {"higher", "lower"}:
            raise SchemaError(f"unsupported direction for metric {name}: {direction}")
        return cls(aggregation=aggregation, direction=direction)


@dataclass(frozen=True)
class SuiteDefinition:
    name: str
    version: str
    primary_metric: str
    metrics: dict[str, MetricDefinition]
    gate: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SuiteDefinition":
        data = _require_mapping(raw, "suite")
        name = _require_string(data.get("name"), "suite.name")
        version = _require_string(data.get("version"), "suite.version")
        primary_metric = _require_string(data.get("primary_metric"), "suite.primary_metric")
        metrics_raw = _require_mapping(data.get("metrics"), "suite.metrics")
        metrics = {
            name_: MetricDefinition.from_dict(name_, definition)
            for name_, definition in metrics_raw.items()
        }
        if primary_metric not in metrics:
            raise SchemaError("suite.primary_metric must be declared in suite.metrics")
        gate = _require_mapping(data.get("gate"), "suite.gate")
        return cls(
            name=name,
            version=version,
            primary_metric=primary_metric,
            metrics=metrics,
            gate=gate,
        )


@dataclass(frozen=True)
class CandidateResponse:
    output: Any
    cost_usd: float
    duration_ms: float
    trace_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, case_id: str, raw: Any) -> "CandidateResponse":
        data = _require_mapping(raw, f"responses.{case_id}")
        cost = data.get("cost_usd", 0.0)
        duration = data.get("duration_ms", 0.0)
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
            raise SchemaError(f"responses.{case_id}.cost_usd must be >= 0")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
            raise SchemaError(f"responses.{case_id}.duration_ms must be >= 0")
        trace_ids_raw = data.get("trace_ids", [])
        if not isinstance(trace_ids_raw, list):
            raise SchemaError(f"responses.{case_id}.trace_ids must be an array")
        trace_ids = tuple(_require_string(item, "trace_ids[]") for item in trace_ids_raw)
        return cls(
            output=data.get("output"),
            cost_usd=float(cost),
            duration_ms=float(duration),
            trace_ids=trace_ids,
        )


@dataclass(frozen=True)
class CandidateProfile:
    name: str
    version: str
    metadata: dict[str, Any]
    responses: dict[str, CandidateResponse]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CandidateProfile":
        data = _require_mapping(raw, "candidate")
        name = _require_string(data.get("name"), "candidate.name")
        version = _require_string(data.get("version"), "candidate.version")
        metadata = _require_mapping(data.get("metadata", {}), "candidate.metadata")
        responses_raw = _require_mapping(data.get("responses"), "candidate.responses")
        responses = {
            case_id: CandidateResponse.from_dict(case_id, response)
            for case_id, response in responses_raw.items()
        }
        return cls(name=name, version=version, metadata=metadata, responses=responses)
