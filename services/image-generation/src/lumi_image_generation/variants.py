from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from .model import ImageGenerationSpec, VariantDecision


class GenerationBudgetError(ValueError):
    pass


def choose_variants(
    spec: ImageGenerationSpec,
    *,
    estimated_cost_per_variant_usd: Decimal,
) -> VariantDecision:
    estimate = estimated_cost_per_variant_usd
    if isinstance(estimate, float) or not estimate.is_finite() or estimate < 0:
        raise ValueError("GENERATION_ESTIMATE_INVALID")
    requested = spec.variant_count
    if estimate == 0:
        return VariantDecision(
            requested,
            requested,
            estimate,
            Decimal("0"),
            ("VARIANT_COUNT_AS_REQUESTED", "ZERO_ESTIMATED_PROVIDER_COST"),
        )
    affordable = int((spec.budget_limit_usd / estimate).to_integral_value(rounding=ROUND_FLOOR))
    if affordable < 1:
        raise GenerationBudgetError("GENERATION_BUDGET_INSUFFICIENT_FOR_ONE_VARIANT")
    selected = min(requested, affordable)
    reasons = (
        ("VARIANT_COUNT_AS_REQUESTED",)
        if selected == requested
        else (
            "VARIANT_COUNT_REDUCED_FOR_BUDGET",
            "HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED",
        )
    )
    return VariantDecision(requested, selected, estimate, estimate * selected, reasons)
