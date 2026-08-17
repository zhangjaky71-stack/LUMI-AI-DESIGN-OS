from __future__ import annotations

from dataclasses import dataclass

from .contracts import ContextLayer, LayerBudget


@dataclass(frozen=True, slots=True)
class ContextProfile:
    name: str
    response_reserve_tokens: int
    retrieval_limit: int
    project_share: int = 25
    task_share: int = 35
    retrieved_share: int = 40

    def layer_budgets(
        self,
        dynamic_budget_tokens: int,
    ) -> tuple[LayerBudget, ...]:
        if dynamic_budget_tokens < 128:
            raise ValueError("CONTEXT_PROFILE_BUDGET_TOO_SMALL")
        shares = self.project_share + self.task_share + self.retrieved_share
        if shares != 100:
            raise ValueError("CONTEXT_PROFILE_SHARE_INVALID")
        project = max(1, dynamic_budget_tokens * self.project_share // 100)
        task = max(1, dynamic_budget_tokens * self.task_share // 100)
        retrieved = max(1, dynamic_budget_tokens - project - task)
        return (
            LayerBudget(ContextLayer.L1_PROJECT, project),
            LayerBudget(ContextLayer.L3_TASK, task, required=True),
            LayerBudget(ContextLayer.L4_RETRIEVED, retrieved),
        )


BALANCED_CONTEXT_PROFILE = ContextProfile(
    name="balanced-v1",
    response_reserve_tokens=2048,
    retrieval_limit=12,
)
