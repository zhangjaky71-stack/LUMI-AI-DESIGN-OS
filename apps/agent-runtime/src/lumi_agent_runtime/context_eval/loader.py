from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    ContextEvalCase,
    ContextEvalExpectation,
    ContextEvalThresholds,
    EvalCategory,
)


def load_eval_corpus(path: Path) -> tuple[str, ContextEvalThresholds, tuple[ContextEvalCase, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != "lumi.context-eval.v1":
        raise ValueError("CONTEXT_EVAL_SCHEMA_INVALID")
    suite_id = _text(raw, "suite_id")
    threshold_raw = raw.get("thresholds", {})
    if not isinstance(threshold_raw, dict):
        raise ValueError("CONTEXT_EVAL_THRESHOLDS_INVALID")
    thresholds = ContextEvalThresholds(
        min_case_pass_rate=float(threshold_raw.get("min_case_pass_rate", 1.0)),
        min_source_recall=float(threshold_raw.get("min_source_recall", 0.95)),
        min_fact_recall=float(threshold_raw.get("min_fact_recall", 0.95)),
        min_provenance_coverage=float(threshold_raw.get("min_provenance_coverage", 1.0)),
        max_forbidden_source_leaks=int(threshold_raw.get("max_forbidden_source_leaks", 0)),
        max_forbidden_phrase_leaks=int(threshold_raw.get("max_forbidden_phrase_leaks", 0)),
        max_token_budget_violations=int(threshold_raw.get("max_token_budget_violations", 0)),
        max_injection_authority_violations=int(
            threshold_raw.get("max_injection_authority_violations", 0)
        ),
        max_freshness_violations=int(threshold_raw.get("max_freshness_violations", 0)),
    )
    rows = raw.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("CONTEXT_EVAL_CASES_INVALID")
    cases = tuple(_parse_case(row) for row in rows)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("CONTEXT_EVAL_CASE_ID_DUPLICATE")
    return suite_id, thresholds, cases


def _parse_case(value: object) -> ContextEvalCase:
    if not isinstance(value, dict):
        raise ValueError("CONTEXT_EVAL_CASE_INVALID")
    expectation = value.get("expectation", {})
    if not isinstance(expectation, dict):
        raise ValueError("CONTEXT_EVAL_EXPECTATION_INVALID")
    metadata = value.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("CONTEXT_EVAL_METADATA_INVALID")
    return ContextEvalCase(
        case_id=_text(value, "case_id"),
        category=EvalCategory(_text(value, "category")),
        description=_text(value, "description"),
        expectation=ContextEvalExpectation(
            required_source_ids=_strings(expectation.get("required_source_ids", [])),
            forbidden_source_ids=_strings(expectation.get("forbidden_source_ids", [])),
            required_facts=_strings(expectation.get("required_facts", [])),
            forbidden_phrases=_strings(expectation.get("forbidden_phrases", [])),
            required_source_versions=_strings(
                expectation.get("required_source_versions", [])
            ),
            max_retrieved_items=(
                int(expectation["max_retrieved_items"])
                if expectation.get("max_retrieved_items") is not None
                else None
            ),
            min_source_recall=float(expectation.get("min_source_recall", 1.0)),
            min_fact_recall=float(expectation.get("min_fact_recall", 1.0)),
        ),
        tags=_strings(value.get("tags", [])),
        metadata=dict(metadata),
    )


def _text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"CONTEXT_EVAL_TEXT_INVALID:{key}")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("CONTEXT_EVAL_STRING_LIST_INVALID")
    return tuple(value)
