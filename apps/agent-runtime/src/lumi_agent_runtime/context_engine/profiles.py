from __future__ import annotations

from .contracts import ContextLayer, LayerBudget


def default_layer_budgets(context_budget_tokens: int) -> tuple[LayerBudget, ...]:
    if context_budget_tokens < 512:
        raise ValueError("CONTEXT_PROFILE_BUDGET_TOO_SMALL")
    weights = {
        ContextLayer.L0_SYSTEM: 0.14,
        ContextLayer.L1_PROJECT: 0.27,
        ContextLayer.L2_AGENT: 0.14,
        ContextLayer.L3_TASK: 0.20,
        ContextLayer.L4_RETRIEVED: 0.25,
    }
    budgets = {
        layer: max(1, int(context_budget_tokens * weight))
        for layer, weight in weights.items()
    }
    remainder = context_budget_tokens - sum(budgets.values())
    budgets[ContextLayer.L4_RETRIEVED] += remainder
    return tuple(
        LayerBudget(
            layer=layer,
            max_tokens=budgets[layer],
            required=layer
            in {
                ContextLayer.L0_SYSTEM,
                ContextLayer.L1_PROJECT,
                ContextLayer.L2_AGENT,
                ContextLayer.L3_TASK,
            },
        )
        for layer in ContextLayer
    )
