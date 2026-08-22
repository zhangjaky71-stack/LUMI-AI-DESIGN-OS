from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import ContextEvalReport


@dataclass(frozen=True, slots=True)
class ContextEvalBaseline:
    suite_id: str
    source_recall: float
    fact_recall: float
    provenance_coverage: float
    pass_rate: float


@dataclass(frozen=True, slots=True)
class RegressionPolicy:
    max_source_recall_drop: float = 0.02
    max_fact_recall_drop: float = 0.02
    max_provenance_drop: float = 0.0
    max_pass_rate_drop: float = 0.0


@dataclass(frozen=True, slots=True)
class RegressionResult:
    passed: bool
    reasons: tuple[str, ...]


def load_baseline(path: str | Path) -> ContextEvalBaseline:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != "lumi.context-eval-baseline.v1":
        raise ValueError("CONTEXT_EVAL_BASELINE_SCHEMA_INVALID")
    suite_id = raw.get("suite_id")
    if not isinstance(suite_id, str) or not suite_id:
        raise ValueError("CONTEXT_EVAL_BASELINE_SUITE_INVALID")

    metrics: dict[str, float] = {}
    for key in ("source_recall", "fact_recall", "provenance_coverage", "pass_rate"):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"CONTEXT_EVAL_BASELINE_METRIC_INVALID:{key}")
        normalized = float(value)
        if not 0.0 <= normalized <= 1.0:
            raise ValueError(f"CONTEXT_EVAL_BASELINE_METRIC_INVALID:{key}")
        metrics[key] = normalized

    return ContextEvalBaseline(
        suite_id=suite_id,
        source_recall=metrics["source_recall"],
        fact_recall=metrics["fact_recall"],
        provenance_coverage=metrics["provenance_coverage"],
        pass_rate=metrics["pass_rate"],
    )


def compare_to_baseline(
    report: ContextEvalReport,
    baseline: ContextEvalBaseline,
    *,
    policy: RegressionPolicy | None = None,
) -> RegressionResult:
    if report.suite_id != baseline.suite_id:
        raise ValueError("CONTEXT_EVAL_BASELINE_SUITE_MISMATCH")
    guard = policy or RegressionPolicy()
    reasons: list[str] = []
    if baseline.source_recall - report.aggregate.source_recall > guard.max_source_recall_drop:
        reasons.append("SOURCE_RECALL_REGRESSION")
    if baseline.fact_recall - report.aggregate.fact_recall > guard.max_fact_recall_drop:
        reasons.append("FACT_RECALL_REGRESSION")
    if baseline.provenance_coverage - report.aggregate.provenance_coverage > guard.max_provenance_drop:
        reasons.append("PROVENANCE_REGRESSION")
    if baseline.pass_rate - report.pass_rate > guard.max_pass_rate_drop:
        reasons.append("CASE_PASS_RATE_REGRESSION")
    return RegressionResult(passed=not reasons, reasons=tuple(reasons))
