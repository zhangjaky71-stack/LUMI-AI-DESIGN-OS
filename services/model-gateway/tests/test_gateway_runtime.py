from __future__ import annotations

import unittest
from decimal import Decimal
from uuid import uuid4

from lumi_model_gateway import (
    AmbiguousProviderOutcomeError,
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
    NoRouteError,
    PaidInvocationGuardRequiredError,
    ResultStatus,
    RetryPolicy,
)
from lumi_model_gateway.telemetry import MemoryCostTelemetrySink
from lumi_model_gateway.testing import (
    InMemoryIdempotentPaidInvocationGuard,
    RecordingPaidInvocationGuard,
    RecordingPaidStreamGuard,
    RecordingSleeper,
)


def request(
    capability: Capability = Capability.LLM_REASONING,
    *,
    budget: Decimal | None = None,
    routing_hints: dict[str, object] | None = None,
    operation_id=None,
) -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        operation_id=operation_id or uuid4(),
        capability=capability,
        inputs={"prompt": "design a quiet luxury coffee poster"},
        budget_limit_usd=budget,
        routing_hints=routing_hints or {},
    )


def runtime(
    *providers: MockProvider,
    paid_guard=None,
    stream_guard=None,
    retry_policy: RetryPolicy | None = None,
    sleeper=None,
):
    registry = InMemoryProviderRegistry(tuple(providers))
    health = InMemoryProviderHealthRegistry()
    router = ModelRouter(registry=registry, health=health)
    telemetry = MemoryCostTelemetrySink()
    guard = paid_guard or RecordingPaidInvocationGuard()
    gateway = ModelGateway(
        registry=registry,
        health=health,
        router=router,
        paid_guard=guard,
        paid_stream_guard=stream_guard,
        retry_policy=retry_policy,
        sleeper=sleeper,
        telemetry=telemetry,
    )
    return gateway, registry, health, telemetry, guard


class GatewayRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_preference_is_soft_weight_not_hard_filter(self) -> None:
        strong = MockProvider(provider="alpha", model="strong", quality_score=95)
        preferred = MockProvider(provider="beta", model="preferred", quality_score=75)
        gateway, _, _, _, _ = runtime(strong, preferred)
        req = request(routing_hints={"preferred_provider": "beta"})
        decision = await gateway.router.route(req)
        self.assertEqual(decision.candidates[0].provider, "beta")
        self.assertTrue(any(item.provider == "alpha" for item in decision.candidates))
        self.assertIn("PREFERRED_PROVIDER", decision.candidates[0].reason_codes)

    async def test_health_filter_removes_unhealthy_primary(self) -> None:
        primary = MockProvider(provider="alpha", model="primary", quality_score=95)
        fallback = MockProvider(provider="beta", model="fallback", quality_score=80)
        gateway, _, health, _, _ = runtime(primary, fallback)
        health.set_unhealthy("alpha", "primary", seconds=60)
        decision = await gateway.router.route(request())
        self.assertEqual(decision.candidates[0].provider, "beta")
        self.assertIn(
            "PROVIDER_UNHEALTHY",
            decision.rejected["alpha:primary"],
        )

    async def test_budget_filter_fails_closed(self) -> None:
        provider = MockProvider()
        gateway, _, _, _, _ = runtime(provider)
        req = request(Capability.IMAGE_GENERATE, budget=Decimal("0.001"))
        with self.assertRaises(NoRouteError):
            await gateway.invoke(req)

    async def test_safe_not_accepted_error_cross_falls_back(self) -> None:
        primary = MockProvider(
            provider="alpha",
            model="primary",
            quality_score=95,
            failures=(
                MockFailure(
                    ErrorCategory.RATE_LIMIT,
                    DeliveryState.NOT_ACCEPTED,
                ),
            ),
        )
        fallback = MockProvider(provider="beta", model="fallback", quality_score=80)
        gateway, _, _, telemetry, guard = runtime(
            primary,
            fallback,
            retry_policy=RetryPolicy(max_attempts_per_provider=1),
        )
        result = await gateway.invoke(request())
        self.assertEqual(result.provider, "beta")
        self.assertEqual([call[1] for call in guard.calls], ["alpha", "beta"])
        self.assertEqual(telemetry.records[0].error_category, "RATE_LIMIT")
        self.assertEqual(telemetry.records[-1].provider, "beta")

    async def test_unknown_delivery_blocks_cross_provider_fallback(self) -> None:
        primary = MockProvider(
            provider="alpha",
            model="primary",
            quality_score=95,
            failures=(
                MockFailure(
                    ErrorCategory.PROVIDER_5XX,
                    DeliveryState.UNKNOWN,
                ),
            ),
        )
        fallback = MockProvider(provider="beta", model="fallback", quality_score=80)
        gateway, _, _, _, guard = runtime(
            primary,
            fallback,
            retry_policy=RetryPolicy(max_attempts_per_provider=1),
        )
        with self.assertRaises(AmbiguousProviderOutcomeError):
            await gateway.invoke(request())
        self.assertEqual([call[1] for call in guard.calls], ["alpha"])

    async def test_provider_retry_obeys_retry_after(self) -> None:
        provider = MockProvider(
            provider="alpha",
            model="retry",
            quality_score=90,
            failures=(
                MockFailure(
                    ErrorCategory.RATE_LIMIT,
                    DeliveryState.NOT_ACCEPTED,
                    retry_after_seconds=1.5,
                ),
            ),
        )
        sleeper = RecordingSleeper()
        gateway, _, _, _, guard = runtime(
            provider,
            retry_policy=RetryPolicy(
                max_attempts_per_provider=2,
                max_delay_seconds=5,
                max_elapsed_seconds=10,
            ),
            sleeper=sleeper,
        )
        result = await gateway.invoke(request())
        self.assertEqual(result.provider, "alpha")
        self.assertEqual(sleeper.delays, [1.5])
        self.assertEqual(len(guard.calls), 2)

    async def test_paid_guard_replays_same_logical_operation(self) -> None:
        provider = MockProvider()
        paid_guard = InMemoryIdempotentPaidInvocationGuard()
        gateway, _, _, _, _ = runtime(provider, paid_guard=paid_guard)
        req = request(operation_id=uuid4())
        first = await gateway.invoke(req)
        second = await gateway.invoke(req)
        self.assertEqual(first, second)
        self.assertEqual(paid_guard.provider_invocations, 1)
        self.assertEqual(paid_guard.replays, 1)

    async def test_stream_is_normalized_and_guarded(self) -> None:
        provider = MockProvider()
        stream_guard = RecordingPaidStreamGuard()
        gateway, _, _, _, _ = runtime(
            provider,
            stream_guard=stream_guard,
        )
        chunks = [chunk async for chunk in gateway.stream(request())]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[-1].kind, "completed")
        self.assertIsNotNone(chunks[-1].usage)
        self.assertEqual(
            [chunk.sequence for chunk in chunks],
            list(range(1, len(chunks) + 1)),
        )
        self.assertEqual(len(stream_guard.calls), 1)

    async def test_async_video_lifecycle(self) -> None:
        provider = MockProvider()
        gateway, _, _, _, _ = runtime(provider)
        req = request(Capability.VIDEO_TEXT_TO_VIDEO)
        pending = await gateway.invoke(req)
        self.assertEqual(pending.status, ResultStatus.PENDING)
        self.assertIsNotNone(pending.provider_request_id)
        provider_request_id = pending.provider_request_id or ""
        still_pending = await gateway.get_async_status(
            provider="mock",
            model="mock-v1",
            provider_request_id=provider_request_id,
        )
        self.assertEqual(still_pending.status, ResultStatus.PENDING)
        completed = await gateway.get_async_status(
            provider="mock",
            model="mock-v1",
            provider_request_id=provider_request_id,
        )
        self.assertEqual(completed.status, ResultStatus.SUCCEEDED)
        self.assertTrue(completed.outputs[0].value.endswith(".mp4"))

    async def test_mock_structured_output_is_deterministic(self) -> None:
        provider = MockProvider()
        req = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_STRUCTURED_OUTPUT,
            inputs={"prompt": "return object"},
            structured_output_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
        )
        first = await provider.invoke(req)
        second = await provider.invoke(req)
        self.assertEqual(first.outputs, second.outputs)
        self.assertEqual(first.outputs[0].kind, "json")

    async def test_api_and_client_do_not_expose_provider_adapter(self) -> None:
        provider = MockProvider()
        gateway, _, _, _, _ = runtime(provider)
        client = ModelGatewayClient(ModelGatewayAPI(gateway))
        result = await client.invoke(request())
        self.assertEqual(result.provider, "mock")
        self.assertFalse(hasattr(client, "registry"))

    async def test_paid_guard_is_required(self) -> None:
        provider = MockProvider()
        registry = InMemoryProviderRegistry((provider,))
        health = InMemoryProviderHealthRegistry()
        router = ModelRouter(registry=registry, health=health)
        with self.assertRaises(PaidInvocationGuardRequiredError):
            ModelGateway(
                registry=registry,
                health=health,
                router=router,
                paid_guard=None,
            )


if __name__ == "__main__":
    unittest.main()
