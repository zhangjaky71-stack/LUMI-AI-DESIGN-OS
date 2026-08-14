from __future__ import annotations

import hashlib

from lumi_agent_runtime.context_engine import ContextLayer, TrustLevel

from .contracts import (
    ContextEvalCase,
    ContextEvalMetrics,
    ContextEvalResult,
    EvaluatedContext,
)


def evaluate_context(case: ContextEvalCase, context: EvaluatedContext) -> ContextEvalResult:
    manifest = context.manifest
    expectation = case.expectation
    selected_source_ids = {item.source.source_id for item in manifest.items}
    selected_source_versions = {
        f"{item.source.source_type}:{item.source.source_id}@{item.source.version}"
        for item in manifest.items
    }

    required_sources = set(expectation.required_source_ids)
    source_hits = len(required_sources & selected_source_ids)
    source_recall = source_hits / len(required_sources) if required_sources else 1.0

    text = context.rendered_text.casefold()
    required_facts = tuple(value.casefold() for value in expectation.required_facts)
    fact_hits = sum(value in text for value in required_facts)
    fact_recall = fact_hits / len(required_facts) if required_facts else 1.0

    forbidden_source_leaks = len(
        selected_source_ids & set(expectation.forbidden_source_ids)
    )
    forbidden_phrase_leaks = sum(
        phrase.casefold() in text for phrase in expectation.forbidden_phrases
    )

    valid_provenance = sum(
        bool(item.source.source_type)
        and bool(item.source.source_id)
        and bool(item.source.version)
        and len(item.source.content_hash) == 64
        for item in manifest.items
    )
    provenance_coverage = (
        valid_provenance / len(manifest.items) if manifest.items else 1.0
    )
    token_budget_violations = int(manifest.total_tokens > manifest.max_tokens)
    injection_authority_violations = sum(
        item.trust == TrustLevel.UNTRUSTED_RETRIEVED
        and item.metadata.get("instruction_authority") != "none"
        for item in manifest.items
    )
    freshness_violations = sum(
        required not in selected_source_versions
        for required in expectation.required_source_versions
    )
    retrieved_item_count = sum(
        item.layer == ContextLayer.L4_RETRIEVED for item in manifest.items
    )

    metrics = ContextEvalMetrics(
        source_recall=source_recall,
        fact_recall=fact_recall,
        forbidden_source_leaks=forbidden_source_leaks,
        forbidden_phrase_leaks=forbidden_phrase_leaks,
        provenance_coverage=provenance_coverage,
        token_budget_violations=token_budget_violations,
        injection_authority_violations=injection_authority_violations,
        freshness_violations=freshness_violations,
        retrieved_item_count=retrieved_item_count,
    )
    reasons: list[str] = []
    if source_recall < expectation.min_source_recall:
        reasons.append("SOURCE_RECALL_BELOW_CASE_THRESHOLD")
    if fact_recall < expectation.min_fact_recall:
        reasons.append("FACT_RECALL_BELOW_CASE_THRESHOLD")
    if forbidden_source_leaks:
        reasons.append("FORBIDDEN_SOURCE_LEAK")
    if forbidden_phrase_leaks:
        reasons.append("FORBIDDEN_PHRASE_LEAK")
    if token_budget_violations:
        reasons.append("TOKEN_BUDGET_VIOLATION")
    if injection_authority_violations:
        reasons.append("INJECTION_AUTHORITY_VIOLATION")
    if freshness_violations:
        reasons.append("SOURCE_FRESHNESS_VIOLATION")
    if (
        expectation.max_retrieved_items is not None
        and retrieved_item_count > expectation.max_retrieved_items
    ):
        reasons.append("RETRIEVED_ITEM_LIMIT_VIOLATION")
    if provenance_coverage < 1:
        reasons.append("PROVENANCE_COVERAGE_INCOMPLETE")

    return ContextEvalResult(
        case_id=case.case_id,
        passed=not reasons,
        metrics=metrics,
        reasons=tuple(reasons),
        manifest_hash=manifest.freeze_hash,
        rendered_hash=hashlib.sha256(context.rendered_text.encode()).hexdigest(),
    )
