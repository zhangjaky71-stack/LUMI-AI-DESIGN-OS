from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.errors import (
    ErrorCategory as ModelErrorCategory,
    ProviderAcceptance,
    ProviderCallError,
)
from lumi_model_gateway.models import (
    Capability,
    CostConfidence,
    CostEstimate,
    HealthSnapshot,
    ModelInput,
    ModelOutput,
    ModelRequest,
    NormalizedResult,
    ProviderModel,
    ResultStatus,
    RouteCandidate,
)

from lumi_api.idempotency.gateway import (
    AmbiguousSideEffect,
    IdempotencyConflict,
    SideEffectGateway,
)
from lumi_api.idempotency.memory import MemoryIdempotencyStore
from lumi_api.model_gateway_side_effects import Node20ModelSideEffectBridge

ORG = UUID("01910000-0000-7000-8000-000000000431")
OP = UUID("01910000-0000-7000-8000-000000000432")
REQ = UUID("01910000-0000-7000-8000-000000000433")


def model_request(text: str = "hello") -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind="text", text=text),),
        budget_limit=Decimal("1"),
    )


def candidate() -> RouteCandidate:
    model = ProviderModel(
        provider="paid-test",
        model="paid-model-v1",
        capabilities=frozenset({Capability.LLM_REASONING}),
        quality_score=90,
        latency_score=80,
        paid=True,
        fixed_request_usd=Decimal("0.01"),
    )
    return RouteCandidate(
        model=model,
        estimate=CostEstimate(Decimal("0.01"), CostConfidence.EXACT),
        health=HealthSnapshot(),
        score=270,
        reason_codes=("test",),
    )


def completed_result() -> NormalizedResult:
    return NormalizedResult(
        status=ResultStatus.COMPLETED,
        provider="paid-test",
        model="paid-model-v1",
        outputs=(ModelOutput(kind="text", text="paid-ok"),),
        provider_request_id="provider-paid-123",
        cost=CostEstimate(Decimal("0.01"), CostConfidence.EXACT),
    )


def bridge():
    store = MemoryIdempotencyStore()
    return (
        Node20ModelSideEffectBridge(
            SideEffectGateway(store),
            lease_owner="node22-test-worker",
        ),
        store,
    )


def test_same_paid_operation_executes_provider_once_and_replays() -> None:
    adapter, _ = bridge()
    calls = 0

    async def effect():
        nonlocal calls
        calls += 1
        return completed_result()

    async def run():
        first = await adapter.execute(
            request=model_request(),
            candidate=candidate(),
            effect=effect,
        )
        second = await adapter.execute(
            request=model_request(),
            candidate=candidate(),
            effect=effect,
        )
        return first, second

    first, second = asyncio.run(run())
    assert calls == 1
    assert first.outputs == second.outputs
    assert second.provider_request_id == "provider-paid-123"


def test_same_operation_candidate_with_different_semantics_conflicts() -> None:
    adapter, _ = bridge()

    async def effect():
        return completed_result()

    async def run():
        await adapter.execute(
            request=model_request("alpha"),
            candidate=candidate(),
            effect=effect,
        )
        await adapter.execute(
            request=model_request("beta"),
            candidate=candidate(),
            effect=effect,
        )

    try:
        asyncio.run(run())
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("same operation with different semantics was replayed")


def test_confirmed_not_accepted_failure_can_recover_without_reconciliation() -> None:
    adapter, store = bridge()
    calls = 0

    async def rejected():
        nonlocal calls
        calls += 1
        raise ProviderCallError(
            ModelErrorCategory.RATE_LIMIT,
            "rate limited",
            provider="paid-test",
            retryable=True,
            acceptance=ProviderAcceptance.NOT_ACCEPTED,
        )

    async def success():
        nonlocal calls
        calls += 1
        return completed_result()

    async def run():
        try:
            await adapter.execute(
                request=model_request(),
                candidate=candidate(),
                effect=rejected,
            )
        except ProviderCallError as exc:
            assert exc.category is ModelErrorCategory.RATE_LIMIT
        else:
            raise AssertionError("confirmed rejection unexpectedly succeeded")
        return await adapter.execute(
            request=model_request(),
            candidate=candidate(),
            effect=success,
        )

    value = asyncio.run(run())
    assert calls == 2
    assert value.outputs[0].text == "paid-ok"
    record = next(iter(store.records.values()))
    assert record.provider_request_id == "provider-paid-123"


def test_unknown_paid_timeout_becomes_ambiguous_and_never_executes_again() -> None:
    adapter, store = bridge()
    calls = 0

    async def timed_out():
        nonlocal calls
        calls += 1
        raise ProviderCallError(
            ModelErrorCategory.TIMEOUT,
            "socket timeout after send",
            provider="paid-test",
            retryable=True,
            acceptance=ProviderAcceptance.UNKNOWN,
        )

    async def should_not_run():
        nonlocal calls
        calls += 1
        return completed_result()

    async def run():
        try:
            await adapter.execute(
                request=model_request(),
                candidate=candidate(),
                effect=timed_out,
            )
        except ProviderCallError:
            pass
        else:
            raise AssertionError("timeout unexpectedly succeeded")
        await adapter.execute(
            request=model_request(),
            candidate=candidate(),
            effect=should_not_run,
        )

    try:
        asyncio.run(run())
    except AmbiguousSideEffect:
        pass
    else:
        raise AssertionError("ambiguous paid timeout was executed again")
    assert calls == 1
    record = next(iter(store.records.values()))
    assert record.error_category is not None
    assert record.error_category.value == "ambiguous"
