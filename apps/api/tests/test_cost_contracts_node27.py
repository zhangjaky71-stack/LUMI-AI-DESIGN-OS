from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from lumi_model_gateway.memory import MemoryBudgetPort
from lumi_model_gateway.models import (
    Capability,
    CostConfidence as ModelCostConfidence,
    CostEstimate,
    HealthSnapshot,
    InputKind,
    ModelInput,
    ModelRequest,
    ModelUsage,
    ProviderModel,
    RouteCandidate,
)

from lumi_api.costs import (
    ActualCost,
    BudgetReservationRequest,
    CostConfidence,
    CostContext,
    UsageFact,
    decimal_amount,
    month_period_key,
)


def test_decimal_money_rejects_float_and_preserves_precision() -> None:
    with pytest.raises(ValueError, match="COST_FLOAT_FORBIDDEN"):
        decimal_amount(0.1)  # type: ignore[arg-type]
    assert decimal_amount("0.12345678") + decimal_amount("0.00000001") == Decimal(
        "0.12345679"
    )


def test_actual_cost_keeps_pricing_provider_and_usage_provenance() -> None:
    context = CostContext(
        organization_id=uuid4(),
        operation_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        generation_id=uuid4(),
    )
    cost = ActualCost(
        context=context,
        provider="provider-a",
        model="model-a",
        amount=Decimal("0.25000000"),
        confidence=CostConfidence.EXACT,
        pricing_snapshot_id="pricing-v9",
        external_provider_request_id="req_123",
        usage=(
            UsageFact(
                metric="llm.input_tokens",
                quantity=Decimal("123"),
                unit="tokens",
            ),
        ),
    )
    assert cost.amount == Decimal("0.25000000")
    assert cost.pricing_snapshot_id == "pricing-v9"
    assert cost.external_provider_request_id == "req_123"
    assert cost.usage[0].quantity == Decimal("123")


def test_budget_reservation_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="COST_RESERVATION_AMOUNT_INVALID"):
        BudgetReservationRequest(
            context=CostContext(
                organization_id=uuid4(),
                operation_id=uuid4(),
            ),
            provider="provider-a",
            model="model-a",
            estimated_amount=Decimal("-0.01"),
        )


def test_month_period_is_utc_stable() -> None:
    at = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
    assert month_period_key(at) == "month:2026-08"


def test_model_semantic_hash_includes_run_and_generation_attribution() -> None:
    base = dict(
        request_id=uuid4(),
        organization_id=uuid4(),
        operation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind=InputKind.TEXT, text="hello"),),
        project_id=uuid4(),
        task_id=uuid4(),
    )
    first = ModelRequest(**base, agent_run_id=uuid4(), generation_id=uuid4())
    second = ModelRequest(
        **{**base, "request_id": uuid4()},
        agent_run_id=uuid4(),
        generation_id=uuid4(),
    )
    assert first.semantic_hash() != second.semantic_hash()


@pytest.mark.asyncio
async def test_budget_settlement_keeps_usage_and_provider_request() -> None:
    budget = MemoryBudgetPort(remaining_usd=Decimal("10"))
    request = ModelRequest(
        request_id=uuid4(),
        organization_id=uuid4(),
        operation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind=InputKind.TEXT, text="hello"),),
    )
    model = ProviderModel(
        provider="fixture",
        model="fixture-1",
        capabilities=frozenset({Capability.LLM_REASONING}),
        paid=False,
    )
    candidate = RouteCandidate(
        model=model,
        estimate=CostEstimate(Decimal("1.00"), ModelCostConfidence.EXACT),
        health=HealthSnapshot(),
        score=100,
        reason_codes=(),
    )
    reservation = await budget.reserve(request, candidate)
    usage = ModelUsage(input_tokens=10, output_tokens=4)
    actual = CostEstimate(Decimal("0.75"), ModelCostConfidence.EXACT)
    await budget.settle(
        reservation,
        actual=actual,
        usage=usage,
        provider_request_id="provider-req-1",
    )
    assert budget.settlements[-1] == (actual, usage, "provider-req-1")
    assert budget.remaining_usd == Decimal("9.25")
