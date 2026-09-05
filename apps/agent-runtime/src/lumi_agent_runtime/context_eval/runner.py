from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import (
    ContextEvalCase,
    ContextEvalReport,
    ContextEvalResult,
    ContextEvalThresholds,
    EvaluatedContext,
)
from .evaluator import evaluate_context
from .suite import evaluate_suite


class ContextEvalExecutor(Protocol):
    async def execute(self, case: ContextEvalCase) -> EvaluatedContext: ...


@dataclass(frozen=True, slots=True)
class DeterminismEvidence:
    case_id: str
    manifest_hash_equal: bool
    rendered_hash_equal: bool

    @property
    def passed(self) -> bool:
        return self.manifest_hash_equal and self.rendered_hash_equal


@dataclass(frozen=True, slots=True)
class ContextEvalRun:
    report: ContextEvalReport
    determinism: tuple[DeterminismEvidence, ...]

    @property
    def passed(self) -> bool:
        return self.report.passed and all(item.passed for item in self.determinism)


async def run_eval_suite(
    suite_id: str,
    cases: tuple[ContextEvalCase, ...],
    *,
    executor: ContextEvalExecutor,
    thresholds: ContextEvalThresholds | None = None,
    verify_determinism: bool = True,
) -> ContextEvalRun:
    if not cases:
        raise ValueError("CONTEXT_EVAL_CASES_EMPTY")
    results: list[ContextEvalResult] = []
    determinism: list[DeterminismEvidence] = []
    for case in cases:
        first_context = await executor.execute(case)
        first = evaluate_context(case, first_context)
        results.append(first)
        if verify_determinism:
            second_context = await executor.execute(case)
            second = evaluate_context(case, second_context)
            determinism.append(
                DeterminismEvidence(
                    case_id=case.case_id,
                    manifest_hash_equal=first.manifest_hash == second.manifest_hash,
                    rendered_hash_equal=first.rendered_hash == second.rendered_hash,
                )
            )
    return ContextEvalRun(
        report=evaluate_suite(
            suite_id,
            tuple(results),
            thresholds=thresholds,
        ),
        determinism=tuple(determinism),
    )
