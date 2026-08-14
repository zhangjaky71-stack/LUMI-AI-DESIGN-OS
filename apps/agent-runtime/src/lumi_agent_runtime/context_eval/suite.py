from __future__ import annotations

from dataclasses import replace
from statistics import fmean

from .contracts import (
    ContextEvalMetrics,
    ContextEvalReport,
    ContextEvalResult,
    ContextEvalThresholds,
)


def evaluate_suite(
    suite_id: str,
    results: tuple[ContextEvalResult, ...],
    *,
    thresholds: ContextEvalThresholds | None = None,
) -> ContextEvalReport:
    if not suite_id or not results:
        raise ValueError("CONTEXT_EVAL_SUITE_INVALID")
    policy = thresholds or ContextEvalThresholds()
    pass_rate = sum(result.passed for result in results) / len(results)
    aggregate = ContextEvalMetrics(
        source_recall=fmean(result.metrics.source_recall for result in results),
        fact_recall=fmean(result.metrics.fact_recall for result in results),
        forbidden_source_leaks=sum(
            result.metrics.forbidden_source_leaks for result in results
        ),
        forbidden_phrase_leaks=sum(
            result.metrics.forbidden_phrase_leaks for result in results
        ),
        provenance_coverage=fmean(
            result.metrics.provenance_coverage for result in results
        ),
        token_budget_violations=sum(
            result.metrics.token_budget_violations for result in results
        ),
        injection_authority_violations=sum(
            result.metrics.injection_authority_violations for result in results
        ),
        freshness_violations=sum(
            result.metrics.freshness_violations for result in results
        ),
        retrieved_item_count=sum(
            result.metrics.retrieved_item_count for result in results
        ),
    )
    passed = (
        pass_rate >= policy.min_case_pass_rate
        and aggregate.source_recall >= policy.min_source_recall
        and aggregate.fact_recall >= policy.min_fact_recall
        and aggregate.provenance_coverage >= policy.min_provenance_coverage
        and aggregate.forbidden_source_leaks <= policy.max_forbidden_source_leaks
        and aggregate.forbidden_phrase_leaks <= policy.max_forbidden_phrase_leaks
        and aggregate.token_budget_violations <= policy.max_token_budget_violations
        and aggregate.injection_authority_violations
        <= policy.max_injection_authority_violations
        and aggregate.freshness_violations <= policy.max_freshness_violations
    )
    return ContextEvalReport(
        suite_id=suite_id,
        results=results,
        thresholds=policy,
        passed=passed,
        aggregate=aggregate,
        pass_rate=pass_rate,
    )
