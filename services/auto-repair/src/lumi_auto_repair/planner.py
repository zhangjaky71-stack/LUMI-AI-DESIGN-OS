from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .model import (
    AutoRepairJob,
    AutoRepairTaskSpec,
    RepairDirective,
    RepairKind,
    RepairPlan,
)


_FREE_KINDS = {
    RepairKind.STRUCTURAL_DESIGN_OP,
    RepairKind.COPY_TYPOGRAPHY_FIX,
}

_ACTION_KIND: dict[str, RepairKind] = {
    "SET_PROPERTY": RepairKind.STRUCTURAL_DESIGN_OP,
    "MOVE_NODE": RepairKind.STRUCTURAL_DESIGN_OP,
    "RESIZE_NODE": RepairKind.STRUCTURAL_DESIGN_OP,
    "SET_FONT": RepairKind.COPY_TYPOGRAPHY_FIX,
    "REPLACE_TEXT": RepairKind.COPY_TYPOGRAPHY_FIX,
    "SET_COLOR": RepairKind.STRUCTURAL_DESIGN_OP,
    "SET_SPACING": RepairKind.STRUCTURAL_DESIGN_OP,
    "REPLACE_ASSET": RepairKind.REGENERATE_ELEMENT,
    "REGENERATE_REGION": RepairKind.LOCAL_IMAGE_EDIT,
    "REGENERATE_ASSET": RepairKind.REGENERATE_ARTIFACT,
}

_KIND_PRIORITY = {
    RepairKind.COPY_TYPOGRAPHY_FIX: 0,
    RepairKind.STRUCTURAL_DESIGN_OP: 1,
    RepairKind.LOCAL_IMAGE_EDIT: 2,
    RepairKind.REGENERATE_ELEMENT: 3,
    RepairKind.REGENERATE_ARTIFACT: 4,
    RepairKind.MANUAL_REVIEW: 99,
}


class DeterministicRepairPlanner:
    """Choose the cheapest safe repair class before any agentic fallback."""

    def plan(
        self,
        *,
        spec: AutoRepairTaskSpec,
        job: AutoRepairJob,
    ) -> RepairPlan:
        iteration = job.next_iteration
        if iteration > spec.policy.max_iterations:
            return self._manual(iteration, "REPAIR_MAX_ITERATIONS_REACHED")

        grouped: dict[RepairKind, list[RepairDirective]] = {}
        for directive in job.current_quality.directives:
            kind = self._kind_for(directive)
            if kind is None or kind not in spec.policy.allowed_kinds:
                continue
            grouped.setdefault(kind, []).append(directive)

        if not grouped:
            return self._manual(iteration, "REPAIR_NO_REGISTERED_SAFE_ACTION")

        candidates = sorted(grouped, key=lambda item: _KIND_PRIORITY[item])
        if not spec.policy.allow_paid_repairs or job.remaining_budget_usd <= 0:
            candidates = [item for item in candidates if item in _FREE_KINDS]
            if not candidates:
                return self._manual(iteration, "REPAIR_BUDGET_EXHAUSTED_NO_FREE_FIX")

        kind = candidates[0]
        directives = tuple(grouped[kind])
        expected_gain = min(
            100.0,
            sum(self._expected_gain(item) for item in directives),
        )
        return RepairPlan(
            iteration=iteration,
            kind=kind,
            directives=directives,
            expected_gain=expected_gain,
            estimated_cost_usd=Decimal("0"),
            paid=kind not in _FREE_KINDS,
            reason_codes=(
                "REPAIR_MINIMUM_REVERSIBLE_ACTION_SELECTED",
                f"REPAIR_KIND:{kind.value}",
            ),
        )

    @staticmethod
    def with_estimate(plan: RepairPlan, amount: Decimal) -> RepairPlan:
        if amount < 0:
            raise ValueError("REPAIR_ESTIMATE_NEGATIVE")
        return replace(plan, estimated_cost_usd=amount)

    @staticmethod
    def _kind_for(directive: RepairDirective) -> RepairKind | None:
        if directive.action_type == "REPLACE_ASSET" and directive.protected_refs:
            return RepairKind.STRUCTURAL_DESIGN_OP
        return _ACTION_KIND.get(directive.action_type)

    @staticmethod
    def _expected_gain(directive: RepairDirective) -> float:
        severity_weight = {
            "HARD": 28.0,
            "ERROR": 18.0,
            "WARNING": 9.0,
            "INFO": 4.0,
        }.get(directive.severity, 6.0)
        if directive.blocking:
            severity_weight += 8.0
        return severity_weight

    @staticmethod
    def _manual(iteration: int, reason: str) -> RepairPlan:
        return RepairPlan(
            iteration=iteration,
            kind=RepairKind.MANUAL_REVIEW,
            directives=(),
            expected_gain=0.0,
            estimated_cost_usd=Decimal("0"),
            paid=False,
            reason_codes=(reason,),
        )
