from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
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

from lumi_api.costs.contracts import ReservationHandle
from lumi_api.costs.model_gateway_adapter import Node27BudgetPort


class FakeCostGateway:
    dsn = "postgresql://unused"

    def __init__(self) -> None:
        self.handle: ReservationHandle | None = None
        self.actual = None
        self.released = None

    async def reserve(self, request):
        self.handle = ReservationHandle(uuid4(), request)
        return self.handle

    async def remaining_budget(self, request):
        del request
        return Decimal("4.25")

    async def commit(self, handle, actual):
        assert handle == self.handle
        self.actual = actual

    async def release(self, handle, *, reason):
        self.released = (handle, reason)


def _request() -> ModelRequest:
    return ModelRequest(
        request_id=uuid4(),
        organization_id=uuid4(),
        operation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind=InputKind.TEXT, text="hello"),),
        project_id=uuid4(),
        task_id=uuid4(),
        agent_run_id=uuid4(),
        generation_id=uuid4(),
    )


def _candidate() -> RouteCandidate:
    model = ProviderModel(
        provider="fixture",
        model="fixture-1",
        capabilities=frozenset({Capability.LLM_REASONING}),
        paid=True,
        pricing_snapshot_id="pricing-1",
        pricing_snapshot_ids=("pricing-1",),
    )
    return RouteCandidate(
        model=model,
        estimate=CostEstimate(
            Decimal("0.50"),
            ModelCostConfidence.EXACT,
            pricing_snapshot_id="pricing-1",
        ),
        health=HealthSnapshot(),
        score=100,
        reason_codes=(),
    )


@pytest.mark.asyncio
async def test_adapter_settlement_maps_cost_usage_and_provider_request() -> None:
    fake = FakeCostGateway()
    port = Node27BudgetPort(fake)  # type: ignore[arg-type]
    reservation = await port.reserve(_request(), _candidate())
    assert reservation.allowed
    assert reservation.remaining_usd == Decimal("4.25")

    await port.settle(
        reservation,
        actual=CostEstimate(
            Decimal("0.42"),
            ModelCostConfidence.EXACT,
            pricing_snapshot_id="pricing-1",
        ),
        usage=ModelUsage(
            input_tokens=10,
            cached_input_tokens=2,
            output_tokens=4,
            requests=1,
        ),
        provider_request_id="provider-request-42",
    )
    assert fake.actual is not None
    assert fake.actual.amount == Decimal("0.42")
    assert fake.actual.external_provider_request_id == "provider-request-42"
    assert fake.actual.context.agent_run_id is not None
    assert fake.actual.context.generation_id is not None
    metrics = {fact.metric for fact in fake.actual.usage}
    assert metrics == {
        "llm.input_tokens",
        "llm.cached_input_tokens",
        "llm.output_tokens",
        "provider.requests",
    }


@pytest.mark.asyncio
async def test_release_is_not_a_financial_write() -> None:
    fake = FakeCostGateway()
    port = Node27BudgetPort(fake)  # type: ignore[arg-type]
    reservation = await port.reserve(_request(), _candidate())
    await port.release(reservation)
    assert fake.actual is None
    assert fake.released is not None
    assert fake.released[1] == "provider_not_accepted"
