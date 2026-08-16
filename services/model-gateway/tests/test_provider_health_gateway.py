from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.errors import (
    ErrorCategory,
    ModelCapabilityTemporarilyUnavailable,
    ProviderAcceptance,
    ProviderCallError,
)
from lumi_model_gateway.gateway import ModelGateway, RetryPolicy
from lumi_model_gateway.memory import (
    MemoryCostTelemetryPort,
    UnlimitedBudgetPort,
    no_sleep,
)
from lumi_model_gateway.models import (
    Capability,
    CostConfidence,
    CostEstimate,
    InputKind,
    ModelInput,
    ModelOutput,
    ModelRequest,
    ModelStreamChunk,
    ModelTiming,
    NormalizedResult,
    ProviderModel,
    ResultStatus,
    StreamEventType,
)
from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthPolicy,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_store import (
    MemoryHealthStateStore,
)
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry


@dataclass
class ManualClock:
    value: float = 1_700_000_000.0

    def now(self) -> float:
        return self.value


class FakeAdapter:
    def __init__(
        self,
        provider: str,
        *,
        fail_category: ErrorCategory | None = None,
    ) -> None:
        self._provider = provider
        self.fail_category = fail_category
        self.invocations = 0
        self._model = ProviderModel(
            provider,
            f"{provider}-llm",
            frozenset({Capability.LLM_REASONING}),
            paid=False,
            fixed_request_usd=Decimal("0.001"),
        )

    @property
    def provider_name(self) -> str:
        return self._provider

    def models(self) -> tuple[ProviderModel, ...]:
        return (self._model,)

    def validate(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> None:
        if request.capability not in model.capabilities:
            raise ValueError("capability mismatch")

    def estimate_cost(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> CostEstimate:
        del request
        return CostEstimate(
            model.fixed_request_usd,
            CostConfidence.EXACT,
            f"{self._provider}-price",
        )

    async def invoke(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> NormalizedResult:
        self.validate(request, model)
        self.invocations += 1
        if self.fail_category is not None:
            raise ProviderCallError(
                self.fail_category,
                "simulated provider failure",
                provider=self._provider,
                retryable=False,
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
            )
        return NormalizedResult(
            ResultStatus.COMPLETED,
            self._provider,
            model.model,
            outputs=(ModelOutput(kind="text", text="ok"),),
            timing=ModelTiming(total_ms=12),
            cost=self.estimate_cost(request, model),
        )

    async def stream(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> AsyncIterator[ModelStreamChunk]:
        del request
        yield ModelStreamChunk(
            StreamEventType.COMPLETED,
            self._provider,
            model.model,
        )

    async def get_async_status(
        self,
        provider_request_id: str,
        model: ProviderModel,
    ) -> NormalizedResult:
        del provider_request_id
        return NormalizedResult(
            ResultStatus.COMPLETED,
            self._provider,
            model.model,
        )

    async def cancel(
        self,
        provider_request_id: str,
        model: ProviderModel,
    ) -> bool:
        del provider_request_id, model
        return True

    def normalize_error(
        self,
        error: BaseException,
    ) -> ProviderCallError:
        if isinstance(error, ProviderCallError):
            return error
        return ProviderCallError(
            ErrorCategory.UNKNOWN,
            str(error),
            provider=self._provider,
        )


def request() -> ModelRequest:
    return ModelRequest(
        request_id=UUID(
            "01910000-0000-7000-8000-000000000701"
        ),
        organization_id=UUID(
            "01910000-0000-7000-8000-000000000702"
        ),
        operation_id=UUID(
            "01910000-0000-7000-8000-000000000703"
        ),
        capability=Capability.LLM_REASONING,
        inputs=(
            ModelInput(
                kind=InputKind.TEXT,
                text="route around failure",
            ),
        ),
        budget_limit=Decimal("1"),
    )


def build_runtime(
    first_failure: ErrorCategory | None,
) -> tuple[
    ModelGateway,
    AdaptiveProviderHealthRegistry,
    FakeAdapter,
    FakeAdapter,
]:
    clock = ManualClock()
    health = AdaptiveProviderHealthRegistry(
        store=MemoryHealthStateStore(now=clock.now),
        clock=clock,
        policy=ProviderHealthPolicy(
            minimum_samples=1,
            max_samples=10,
            window_seconds=60,
            state_ttl_seconds=300,
            consecutive_failures_open=1,
            open_cooldown_seconds=30,
        ),
    )
    first = FakeAdapter(
        "provider-a",
        fail_category=first_failure,
    )
    second = FakeAdapter("provider-b")
    registry = ProviderRegistry()
    registry.register(first)
    registry.register(second)
    router = ModelRouter(registry, health)
    gateway = ModelGateway(
        registry=registry,
        router=router,
        budget=UnlimitedBudgetPort(),
        telemetry=MemoryCostTelemetryPort(),
        retry_policy=RetryPolicy(
            max_attempts_per_provider=1,
        ),
        sleep=no_sleep,
    )
    return gateway, health, first, second


def test_gateway_falls_back_then_excludes_open_provider() -> None:
    gateway, health, first, second = build_runtime(
        ErrorCategory.PROVIDER_5XX
    )
    result = asyncio.run(gateway.invoke(request()))
    assert result.provider == "provider-b"
    assert first.invocations == 1
    assert second.invocations == 1
    assert health.fallback_total == 1
    assert health.detailed_snapshot(
        "provider-a",
        "provider-a-llm",
        Capability.LLM_REASONING.value,
    ).state is ProviderHealthState.OPEN_CIRCUIT

    second_result = asyncio.run(gateway.invoke(request()))
    assert second_result.provider == "provider-b"
    assert first.invocations == 1
    assert second.invocations == 2


def test_all_open_routes_raise_explicit_temporary_unavailable() -> None:
    gateway, health, first, second = build_runtime(None)
    for adapter in (first, second):
        health.record_failure(
            adapter.provider_name,
            adapter.models()[0].model,
            ErrorCategory.PROVIDER_5XX.value,
            capability=Capability.LLM_REASONING.value,
        )
    try:
        asyncio.run(gateway.invoke(request()))
    except ModelCapabilityTemporarilyUnavailable as exc:
        assert (
            "MODEL_CAPABILITY_TEMPORARILY_UNAVAILABLE"
            in str(exc)
        )
    else:
        raise AssertionError(
            "all-open route did not raise temporary unavailable"
        )
    assert health.all_candidates_unavailable_total == 1


def test_invalid_request_does_not_open_provider() -> None:
    gateway, health, first, _ = build_runtime(
        ErrorCategory.INVALID_REQUEST
    )
    try:
        asyncio.run(gateway.invoke(request()))
    except ProviderCallError as exc:
        assert exc.category is ErrorCategory.INVALID_REQUEST
    else:
        raise AssertionError(
            "invalid request was not propagated"
        )
    snapshot = health.detailed_snapshot(
        first.provider_name,
        first.models()[0].model,
        Capability.LLM_REASONING.value,
    )
    assert snapshot.state is ProviderHealthState.UNKNOWN
    assert snapshot.sample_count == 0
