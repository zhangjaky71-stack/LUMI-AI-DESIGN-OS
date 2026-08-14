from __future__ import annotations

from dataclasses import dataclass

from .contracts import ContextEvalMetrics, ContextEvalReport


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
