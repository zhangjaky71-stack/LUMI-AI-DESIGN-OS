from __future__ import annotations

import asyncio
from uuid import uuid4

from lumi_model_gateway import (
    Capability,
    DeliveryState,
    ErrorCategory,
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockFailure,
    MockProvider,
    ModelGateway,
    ModelGatewayAPI,
    ModelGatewayClient,
    ModelRequest,
    ModelRouter,
    ResultStatus,
    RetryPolicy,
)
from lumi_model_gateway.testing import (
    InMemoryIdempotentPaidInvocationGuard,
    RecordingPaidInvocationGuard,
    RecordingPaidStreamGuard,
)


def build_gateway(
    *providers: MockProvider,
    paid_guard=None,
    stream_guard=None,
    retries: int = 1,
) -> ModelGateway:
    registry = InMemoryProviderRegistry(tuple(providers))
    health = InMemoryProviderHealthRegistry()
    return ModelGateway(
        registry=registry,
        health=health,
        router=ModelRouter(registry=registry, health=health),
        paid_guard=paid_guard or RecordingPaidInvocationGuard(),
        paid_stream_guard=stream_guard,
        retry_policy=RetryPolicy(max_attempts_per_provider=retries),
    )


def model_request(capability: Capability, *, operation_id=None) -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        operation_id=operation_id or uuid4(),
        capability=capability,
        inputs={"prompt": "node22 deterministic integration"},
    )


async def safe_fallback_acceptance() -> None:
    primary = MockProvider(
        provider="primary",
        model="mock-primary",
        quality_score=95,
        failures=(
            MockFailure(
                ErrorCategory.RATE_LIMIT,
                DeliveryState.NOT_ACCEPTED,
            ),
        ),
    )
    fallback = MockProvider(
        provider="fallback",
        model="mock-fallback",
        quality_score=80,
    )
    gateway = build_gateway(primary, fallback)
    result = await gateway.invoke(model_request(Capability.LLM_REASONING))
    assert result.provider == "fallback"


async def capability_acceptance() -> None:
    provider = MockProvider()
    gateway = build_gateway(provider)
    client = ModelGatewayClient(ModelGatewayAPI(gateway))
    image = await client.invoke(model_request(Capability.IMAGE_GENERATE))
    assert image.outputs[0].value.startswith("fixture://mock/image/")

    video = await client.invoke(model_request(Capability.VIDEO_TEXT_TO_VIDEO))
    assert video.status == ResultStatus.PENDING
    provider_request_id = video.provider_request_id or ""
    await client.get_async_status(
        provider="mock",
        model="mock-v1",
        provider_request_id=provider_request_id,
    )
    completed = await client.get_async_status(
        provider="mock",
        model="mock-v1",
        provider_request_id=provider_request_id,
    )
    assert completed.status == ResultStatus.SUCCEEDED
    assert completed.outputs[0].value.endswith(".mp4")


async def stream_acceptance() -> None:
    provider = MockProvider()
    stream_guard = RecordingPaidStreamGuard()
    gateway = build_gateway(provider, stream_guard=stream_guard)
    chunks = [
        chunk
        async for chunk in gateway.stream(model_request(Capability.LLM_REASONING))
    ]
    assert chunks[-1].kind == "completed"
    assert chunks[-1].usage is not None
    assert len(stream_guard.calls) == 1


async def idempotent_paid_acceptance() -> None:
    provider = MockProvider()
    guard = InMemoryIdempotentPaidInvocationGuard()
    gateway = build_gateway(provider, paid_guard=guard)
    operation_id = uuid4()
    organization_id = uuid4()
    request = ModelRequest(
        organization_id=organization_id,
        operation_id=operation_id,
        capability=Capability.LLM_REASONING,
        inputs={"prompt": "same paid logical operation"},
    )
    first, second = await asyncio.gather(
        gateway.invoke(request),
        gateway.invoke(request),
    )
    assert first == second
    assert guard.provider_invocations == 1
    assert guard.replays == 1


async def main_async() -> None:
    await safe_fallback_acceptance()
    await capability_acceptance()
    await stream_acceptance()
    await idempotent_paid_acceptance()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-22 model gateway mock/integration acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
