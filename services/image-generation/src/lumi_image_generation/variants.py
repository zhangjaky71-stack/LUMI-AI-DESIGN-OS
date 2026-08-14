from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR

from .model import ImageGenerationSpec, VariantDecision


class GenerationBudgetError(ValueError):
    pass


def choose_variants(
    spec: ImageGenerationSpec,
    *,
    estimated_cost_per_variant_usd: Decimal,
) -> VariantDecision:
    if isinstance(estimated_cost_per_variant_usd, float):
        raise ValueError("GENERATION_ESTIMATE_FLOAT_FORBIDDEN")
    if not estimated_cost_per_variant_usd.is_finite() or estimated_cost_per_variant_usd < 0:
        raise ValueError("GENERATION_ESTIMATE_INVALID")

    requested = spec.variant_count
    if estimated_cost_per_variant_usd == 0:
        return VariantDecision(
            requested_count=requested,
            selected_count=requested,
            estimated_cost_per_variant_usd=estimated_cost_per_variant_usd,
            estimated_total_usd=Decimal("0"),
            reason_codes=("VARIANT_COUNT_AS_REQUESTED", "ZERO_ESTIMATED_PROVIDER_COST"),
        )

    affordable = int(
        (spec.budget_limit_usd / estimated_cost_per_variant_usd).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    if affordable < 1:
        raise GenerationBudgetError("GENERATION_BUDGET_INSUFFICIENT_FOR_ONE_VARIANT")

    selected = min(requested, affordable)
    reasons = ["VARIANT_COUNT_AS_REQUESTED"]
    if selected < requested:
        reasons = [
            "VARIANT_COUNT_REDUCED_FOR_BUDGET",
            "HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED",
        ]

    return VariantDecision(
        requested_count=requested,
        selected_count=selected,
        estimated_cost_per_variant_usd=estimated_cost_per_variant_usd,
        estimated_total_usd=estimated_cost_per_variant_usd * selected,
        reason_codes=tuple(reasons),
    )
