from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.errors import (
    ErrorCategory,
    ProviderAcceptance,
    ProviderCallError,
    UnsupportedProviderOperation,
)
from lumi_model_gateway.gateway import ModelGateway, RetryPolicy
from lumi_model_gateway.memory import (
    MemoryBudgetPort,
    MemoryCostTelemetryPort,
    MemoryHealthPort,
    MemoryPaidSideEffectPort,
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
    NormalizedResult,
    ProviderModel,
    ResultStatus,
    RoutingHints,
)
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry

ORG = UUID("01910000-0000-7000-8000-000000000411")
OP = UUID("01910000-0000-7000-8000-000000000412")
REQ = UUID("01910000-0000-7000-8000-000000000413")


class ScriptedProvider:
    def __init__(
        self,
        name: str,
        script: list[NormalizedResult | ProviderCallError],
        *,
        paid: bool,
        quality: int,
    ) -> None:
        self.provider_name = name
        self.script = list(script)
        self.calls = 0
        self._model = ProviderModel(
            provider=name,
            model=f"{name}-model",
            capabilities=frozenset({Capability.LLM_REASONING}),
            quality_score=quality,
            latency_score=90,
            paid=paid,
            fixed_request_usd=Decimal("0.01"),
        )

    def models(self) -> tuple[ProviderModel, ...]:
        return (self._model,)

    def validate(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> None:
        del request, model

    def estimate_cost(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> CostEstimate:
        del request, model
        return CostEstimate(
            Decimal("0.01"),
            CostConfidence.EXACT,
        )

    async def invoke(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> NormalizedResult:
        del request, model
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, ProviderCallError):
            raise item
        return item

    async def stream(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> AsyncIterator[ModelStreamChunk]:
        del request, model
        raise UnsupportedProviderOperation("not used")
        yield

    async def get_async_status(
        self,
        provider_request_id: str,
        model: ProviderModel,
    ) -> NormalizedResult:
        del provider_request_id, model
        raise UnsupportedProviderOperation("not used")

    async def cancel(
        self,
        provider_request_id: str,
        model: ProviderModel,
    ) -> bool:
        del provider_request_id, model
        return False

    def normalize_error(
        self,
        error: BaseException,
    ) -> ProviderCallError:
        assert isinstance(error, ProviderCallError)
        return error


def result(provider: str) -> NormalizedResult:
    return NormalizedResult(
        ResultStatus.COMPLETED,
        provider,
        f"{provider}-model",
        outputs=(ModelOutput(kind="text", text=provider),),
        provider_request_id=f"{provider}-request",
        cost=CostEstimate(
            Decimal("0.01"),
            CostConfidence.EXACT,
        ),
    )


def error(
    category: ErrorCategory,
    *,
    acceptance: ProviderAcceptance,
    retryable: bool,
) -> ProviderCallError:
    return ProviderCallError(
        category,
        category.value,
        retryable=retryable,
        acceptance=acceptance,
    )


def request(
    *,
    preferred: str,
    allow_fallback: bool = True,
) -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=Capability.LLM_REASONING,
        inputs=(
            ModelInput(
                kind=InputKind.TEXT,
                text="hello",
            ),
        ),
        budget_limit=Decimal("1"),
        routing_hints=RoutingHints(
            preferred_providers=(preferred,),
            allow_fallback=allow_fallback,
        ),
    )


def gateway(
    primary: ScriptedProvider,
    backup: ScriptedProvider,
) -> ModelGateway:
    registry = ProviderRegistry()
    registry.register(primary)
    registry.register(backup)
    return ModelGateway(
        registry=registry,
        router=ModelRouter(registry, MemoryHealthPort()),
        budget=MemoryBudgetPort(Decimal("10")),
        telemetry=MemoryCostTelemetryPort(),
        paid_side_effects=MemoryPaidSideEffectPort(),
        retry_policy=RetryPolicy(max_attempts_per_provider=1),
    )


def test_paid_confirmed_rejection_can_fallback() -> None:
    primary = ScriptedProvider(
        "primary",
        [
            error(
                ErrorCategory.RATE_LIMIT,
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
                retryable=True,
            )
        ],
        paid=True,
        quality=95,
    )
    backup = ScriptedProvider(
        "backup",
        [result("backup")],
        paid=True,
        quality=80,
    )
    value = asyncio.run(
        gateway(primary, backup).invoke(
            request(preferred="primary")
        )
    )
    assert value.provider == "backup"
    assert primary.calls == 1
    assert backup.calls == 1


def test_paid_unknown_timeout_never_cross_provider_fallbacks() -> None:
    primary = ScriptedProvider(
        "primary",
        [
            error(
                ErrorCategory.TIMEOUT,
                acceptance=ProviderAcceptance.UNKNOWN,
                retryable=True,
            )
        ],
        paid=True,
        quality=95,
    )
    backup = ScriptedProvider(
        "backup",
        [result("backup")],
        paid=True,
        quality=80,
    )
    try:
        asyncio.run(
            gateway(primary, backup).invoke(
                request(preferred="primary")
            )
        )
    except ProviderCallError as exc:
        assert exc.category is ErrorCategory.TIMEOUT
    else:
        raise AssertionError(
            "ambiguous paid timeout incorrectly fell back"
        )
    assert primary.calls == 1
    assert backup.calls == 0


def test_auth_error_never_fallbacks_but_unpaid_timeout_can() -> None:
    auth_primary = ScriptedProvider(
        "primary",
        [
            error(
                ErrorCategory.AUTH_ERROR,
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
                retryable=False,
            )
        ],
        paid=False,
        quality=95,
    )
    backup = ScriptedProvider(
        "backup",
        [result("backup")],
        paid=False,
        quality=80,
    )
    try:
        asyncio.run(
            gateway(auth_primary, backup).invoke(
                request(preferred="primary")
            )
        )
    except ProviderCallError as exc:
        assert exc.category is ErrorCategory.AUTH_ERROR
    else:
        raise AssertionError("auth error incorrectly fell back")
    assert backup.calls == 0

    timeout_primary = ScriptedProvider(
        "primary",
        [
            error(
                ErrorCategory.TIMEOUT,
                acceptance=ProviderAcceptance.UNKNOWN,
                retryable=True,
            )
        ],
        paid=False,
        quality=95,
    )
    timeout_backup = ScriptedProvider(
        "backup",
        [result("backup")],
        paid=False,
        quality=80,
    )
    value = asyncio.run(
        gateway(timeout_primary, timeout_backup).invoke(
            request(preferred="primary")
        )
    )
    assert value.provider == "backup"
