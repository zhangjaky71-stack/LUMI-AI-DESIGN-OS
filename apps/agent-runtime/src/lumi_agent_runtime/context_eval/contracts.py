from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from lumi_agent_runtime.context_engine import ContextManifest


class EvalCategory(StrEnum):
    SOURCE_RECALL = "SOURCE_RECALL"
    FACT_RETENTION = "FACT_RETENTION"
    TENANT_ISOLATION = "TENANT_ISOLATION"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    TOKEN_BUDGET = "TOKEN_BUDGET"
    FRESHNESS = "FRESHNESS"
    DISTRACTOR_RESILIENCE = "DISTRACTOR_RESILIENCE"
    PROVENANCE = "PROVENANCE"


@dataclass(frozen=True, slots=True)
class ContextEvalExpectation:
    required_source_ids: tuple[str, ...] = ()
    forbidden_source_ids: tuple[str, ...] = ()
    required_facts: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = ()
    required_source_versions: tuple[str, ...] = ()
    max_retrieved_items: int | None = None
    min_source_recall: float = 1.0
    min_fact_recall: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.min_source_recall <= 1 or not 0 <= self.min_fact_recall <= 1:
            raise ValueError("CONTEXT_EVAL_THRESHOLD_INVALID")
        if self.max_retrieved_items is not None and self.max_retrieved_items < 0:
            raise ValueError("CONTEXT_EVAL_RETRIEVAL_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class ContextEvalCase:
    case_id: str
    category: EvalCategory
    description: str
    expectation: ContextEvalExpectation
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_id or not self.description:
            raise ValueError("CONTEXT_EVAL_CASE_INVALID")


@dataclass(frozen=True, slots=True)
class ContextEvalMetrics:
    source_recall: float
    fact_recall: float
    forbidden_source_leaks: int
    forbidden_phrase_leaks: int
    provenance_coverage: float
    token_budget_violations: int
    injection_authority_violations: int
    freshness_violations: int
    retrieved_item_count: int


@dataclass(frozen=True, slots=True)
class ContextEvalResult:
    case_id: str
    passed: bool
    metrics: ContextEvalMetrics
    reasons: tuple[str, ...]
    manifest_hash: str
    rendered_hash: str


@dataclass(frozen=True, slots=True)
class ContextEvalThresholds:
    min_case_pass_rate: float = 1.0
    min_source_recall: float = 0.95
    min_fact_recall: float = 0.95
    min_provenance_coverage: float = 1.0
    max_forbidden_source_leaks: int = 0
    max_forbidden_phrase_leaks: int = 0
    max_token_budget_violations: int = 0
    max_injection_authority_violations: int = 0
    max_freshness_violations: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.min_case_pass_rate,
            self.min_source_recall,
            self.min_fact_recall,
            self.min_provenance_coverage,
        ):
            if not 0 <= value <= 1:
                raise ValueError("CONTEXT_EVAL_SUITE_THRESHOLD_INVALID")


@dataclass(frozen=True, slots=True)
class ContextEvalReport:
    suite_id: str
    results: tuple[ContextEvalResult, ...]
    thresholds: ContextEvalThresholds
    passed: bool
    aggregate: ContextEvalMetrics
    pass_rate: float


@dataclass(frozen=True, slots=True)
class EvaluatedContext:
    manifest: ContextManifest
    rendered_text: str
