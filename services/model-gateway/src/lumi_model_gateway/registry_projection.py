from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from .models import Capability, ProviderModel
from .registry import (
    CapabilitySupport,
    ModelRecord,
    PricingSnapshot,
    registry_checksum,
)

_INPUT_METRICS = (
    "input_tokens",
    "standard_input_tokens",
    "text_input_tokens",
)
_OUTPUT_METRICS = (
    "output_tokens",
    "standard_output_tokens",
)
_FIXED_REQUEST_METRICS = (
    "request",
    "fixed_request",
)


def provider_model_from_record(
    record: ModelRecord,
    *,
    registry_snapshot_id: str,
    pricing_at: datetime | None = None,
) -> ProviderModel:
    capabilities = frozenset(
        claim.capability
        for claim in record.claims
        if claim.support
        in {CapabilitySupport.FULL, CapabilitySupport.PARTIAL}
    )
    if not capabilities:
        raise ValueError(
            "registry model has no executable capability claims: "
            f"{record.model_key}"
        )

    at_time = pricing_at or datetime.now(UTC)
    live_prices = record.pricing(at_time)
    input_price = _first_price(
        live_prices,
        _INPUT_METRICS,
        required_unit="per_million",
    )
    output_price = _first_price(
        live_prices,
        _OUTPUT_METRICS,
        required_unit="per_million",
    )
    fixed_price = _first_price(
        live_prices,
        _FIXED_REQUEST_METRICS,
        required_unit="per_request",
    )
    selected = tuple(
        price
        for price in (
            input_price,
            output_price,
            fixed_price,
        )
        if price is not None
    )
    snapshot_ids = tuple(
        price.pricing_snapshot_id
        for price in selected
    )
    composite_id = (
        "registry-pricing:"
        + registry_checksum(tuple(sorted(snapshot_ids)))[:16]
        if snapshot_ids
        else None
    )

    return ProviderModel(
        provider=record.provider,
        model=record.model,
        capabilities=capabilities,
        quality_score=50,
        latency_score=50,
        regions=record.regions,
        paid=True,
        input_usd_per_million=(
            None if input_price is None else input_price.price
        ),
        output_usd_per_million=(
            None if output_price is None else output_price.price
        ),
        fixed_request_usd=(
            None if fixed_price is None else fixed_price.price
        ),
        enabled=record.route_eligible,
        registry_snapshot_id=registry_snapshot_id,
        model_revision_id=record.revision_id or record.model_key,
        pricing_snapshot_id=composite_id,
        pricing_snapshot_ids=snapshot_ids,
        quality_measured=False,
        latency_measured=False,
    )


def _first_price(
    prices: tuple[PricingSnapshot, ...],
    metric_preference: tuple[str, ...],
    *,
    required_unit: str,
) -> PricingSnapshot | None:
    by_metric: dict[str, list[PricingSnapshot]] = {}
    for price in prices:
        if price.unit != required_unit:
            continue
        by_metric.setdefault(price.metric, []).append(price)
    for metric in metric_preference:
        matches = by_metric.get(metric)
        if not matches:
            continue
        return max(
            matches,
            key=lambda item: item.effective_from,
        )
    return None


def pricing_projection_complete_for_capability(
    model: ProviderModel,
    capability: Capability,
) -> bool:
    if capability in {
        Capability.LLM_REASONING,
        Capability.LLM_STRUCTURED_OUTPUT,
        Capability.LLM_VISION,
    }:
        return (
            model.input_usd_per_million is not None
            and model.output_usd_per_million is not None
        )
    return model.fixed_request_usd is not None


def projected_token_cost(
    model: ProviderModel,
    *,
    input_tokens: int,
    output_tokens: int,
) -> Decimal | None:
    if (
        model.input_usd_per_million is None
        or model.output_usd_per_million is None
    ):
        return None
    return (
        Decimal(input_tokens)
        * model.input_usd_per_million
        / Decimal(1_000_000)
        + Decimal(output_tokens)
        * model.output_usd_per_million
        / Decimal(1_000_000)
    )
