from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.memory import (
    MemoryBudgetPort,
    MemoryCostTelemetryPort,
    MemoryHealthPort,
    MemoryPaidSideEffectPort,
)
from lumi_model_gateway.mock_provider import MockProvider
from lumi_model_gateway.models import (
    Capability,
    CostConfidence,
    CostEstimate,
    HealthSnapshot,
    InputKind,
    ModelInput,
    ModelOutput,
    ModelRequest,
    NormalizedResult,
    ProviderModel,
    ResultStatus,
    RouteCandidate,
    RoutingHints,
    StreamEventType,
)
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry
from lumi_model_gateway.serialization import result_from_dict, result_to_dict

ORG = UUID("01910000-0000-7000-8000-000000000401")
OP = UUID("01910000-0000-7000-8000-000000000402")
REQ = UUID("01910000-0000-7000-8000-000000000403")


def request(
    capability: Capability = Capability.LLM_REASONING,
    *,
    budget: Decimal | None = Decimal("1"),
    constraints: dict | None = None,
    hints: RoutingHints | None = None,
    schema: dict | None = None,
) -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=capability,
        inputs=(
            ModelInput(
                kind=InputKind.TEXT,
                text="design a landing page",
            ),
        ),
        budget_limit=budget,
        constraints=dict(constraints or {}),
        routing_hints=hints or RoutingHints(),
        structured_output_schema=schema,
    )


def build_gateway():
    provider = MockProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    health = MemoryHealthPort()
    budget = MemoryBudgetPort(Decimal("10"))
    telemetry = MemoryCostTelemetryPort()
    gateway = ModelGateway(
        registry=registry,
        router=ModelRouter(registry, health),
        budget=budget,
        telemetry=telemetry,
    )
    return gateway, provider, health, telemetry


def test_route_by_capability_and_budget_health_filters() -> None:
    gateway, _, health, _ = build_gateway()
    decision = gateway.router.route(request())
    assert decision.candidates[0].model.model == "mock-llm-v1"
    assert "capability_match" in decision.candidates[0].reason_codes

    too_small = gateway.router.route(
        request(budget=Decimal("0.00001"))
    )
    assert not too_small.candidates
    assert any(
        "budget_filtered" in reason
        for reason in too_small.rejected_reason_codes
    )

    health.set(
        "mock",
        "mock-llm-v1",
        HealthSnapshot(False, 0, "down"),
    )
    unhealthy = gateway.router.route(request())
    assert not unhealthy.candidates
    assert any(
        "health_filtered" in reason
        for reason in unhealthy.rejected_reason_codes
    )


def test_mock_structured_response_is_deterministic_and_telemetry_records() -> None:
    gateway, provider, _, telemetry = build_gateway()
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "score": {"type": "integer"},
        },
        "required": ["title", "score"],
    }
    req = request(Capability.LLM_STRUCTURED_OUTPUT, schema=schema)

    async def run():
        first = await gateway.invoke(req)
        second = await gateway.invoke(req)
        return first, second

    first, second = asyncio.run(run())
    assert first.outputs[0].json_value == {
        "score": 1,
        "title": "mock",
    }
    assert second.outputs == first.outputs
    assert provider.invocations == 2
    assert len(telemetry.records) == 2


def test_standard_stream_chunks_and_async_video_lifecycle() -> None:
    gateway, _, health, telemetry = build_gateway()

    async def run():
        chunks = [chunk async for chunk in gateway.stream(request())]
        video = await gateway.invoke(
            request(Capability.VIDEO_TEXT_TO_VIDEO)
        )
        assert video.provider_request_id is not None
        first = await gateway.get_async_status(
            provider=video.provider,
            model=video.model,
            provider_request_id=video.provider_request_id,
        )
        second = await gateway.get_async_status(
            provider=video.provider,
            model=video.model,
            provider_request_id=video.provider_request_id,
        )
        return chunks, video, first, second

    chunks, video, first, second = asyncio.run(run())
    assert chunks[0].event is StreamEventType.STARTED
    assert chunks[-1].event is StreamEventType.COMPLETED
    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert text.startswith("mock:")
    assert video.status is ResultStatus.PENDING
    assert first.status is ResultStatus.PENDING
    assert second.status is ResultStatus.COMPLETED
    assert second.outputs[0].asset_ref is not None
    assert second.outputs[0].asset_ref.endswith(".mp4")
    assert health.successes[("mock", "mock-llm-v1")] == 1
    assert telemetry.records[0].result.usage.input_tokens == 7


def test_semantic_hash_is_order_stable_and_rejects_non_finite_values() -> None:
    left = request(constraints={"tags": {"b", "a"}})
    right = request(constraints={"tags": {"a", "b"}})
    assert left.semantic_hash() == right.semantic_hash()

    bad = request(constraints={"temperature": float("nan")})
    try:
        bad.semantic_hash()
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("non-finite semantic input was accepted")


def test_normalized_result_round_trip_preserves_decimal_usage_and_outputs() -> None:
    value = NormalizedResult(
        status=ResultStatus.COMPLETED,
        provider="roundtrip",
        model="model-v1",
        outputs=(
            ModelOutput(
                kind="json",
                json_value={"ok": True},
                asset_ref="asset://result",
            ),
        ),
        provider_request_id="req-123",
        cost=CostEstimate(
            Decimal("0.012345"),
            CostConfidence.EXACT,
            "price-snapshot",
        ),
    )
    restored = result_from_dict(result_to_dict(value))
    assert restored == value


def test_durable_result_json_normalizes_uuid_decimal_and_sets() -> None:
    value = NormalizedResult(
        status=ResultStatus.COMPLETED,
        provider="json-safe",
        model="model-v1",
        outputs=(
            ModelOutput(
                kind="json",
                json_value={
                    "operation": OP,
                    "amount": Decimal("1.25"),
                },
            ),
        ),
        safety_metadata={"labels": {"safe", "review"}},
        cost=CostEstimate(
            Decimal("0.5"),
            CostConfidence.EXACT,
            detail={"trace": REQ},
        ),
    )
    encoded = result_to_dict(value)
    json.dumps(encoded, allow_nan=False)
    assert encoded["outputs"][0]["json_value"] == {
        "operation": str(OP),
        "amount": "1.25",
    }
    assert encoded["safety_metadata"]["labels"] == ["review", "safe"]
    assert encoded["cost"]["detail"]["trace"] == str(REQ)


def test_memory_paid_reference_rejects_semantic_reuse() -> None:
    paid = MemoryPaidSideEffectPort()
    model = ProviderModel(
        provider="paid-memory",
        model="model-v1",
        capabilities=frozenset({Capability.LLM_REASONING}),
        paid=True,
    )
    candidate = RouteCandidate(
        model=model,
        estimate=CostEstimate(None, CostConfidence.UNKNOWN),
        health=HealthSnapshot(),
        score=100,
        reason_codes=("test",),
    )
    first = request(constraints={"version": 1})
    second = request(constraints={"version": 2})

    async def effect() -> NormalizedResult:
        return NormalizedResult(
            ResultStatus.COMPLETED,
            "paid-memory",
            "model-v1",
        )

    async def run() -> None:
        await paid.execute(
            request=first,
            candidate=candidate,
            effect=effect,
        )
        await paid.execute(
            request=second,
            candidate=candidate,
            effect=effect,
        )

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        assert "SEMANTIC_CONFLICT" in str(exc)
    else:
        raise AssertionError("semantic mismatch reused paid memory result")
