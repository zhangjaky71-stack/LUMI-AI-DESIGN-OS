from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from .errors import (
    FALLBACK_ALLOWED,
    ErrorCategory,
    NoRouteAvailable,
    PaidSideEffectGuardRequired,
    ProviderAcceptance,
    ProviderCallError,
)
from .models import ModelRequest, ModelStreamChunk, NormalizedResult, RouteCandidate
from .ports import (
    BudgetPort,
    CostTelemetry,
    CostTelemetryPort,
    PaidSideEffectPort,
    SleepPort,
)
from .routing import ModelRouter, ProviderRegistry


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts_per_provider: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0
    max_elapsed_seconds: float = 15.0

    def __post_init__(self) -> None:
        if self.max_attempts_per_provider < 1:
            raise ValueError("max_attempts_per_provider must be >= 1")


class ModelGateway:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        router: ModelRouter,
        budget: BudgetPort,
        telemetry: CostTelemetryPort,
        paid_side_effects: PaidSideEffectPort | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: SleepPort = asyncio.sleep,
        random_source: random.Random | None = None,
    ) -> None:
        self.registry = registry
        self.router = router
        self.budget = budget
        self.telemetry = telemetry
        self.paid_side_effects = paid_side_effects
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleep = sleep
        self.random = random_source or random.Random()

    async def invoke(self, request: ModelRequest) -> NormalizedResult:
        decision = self.router.route(request)
        if not decision.candidates:
            raise NoRouteAvailable(
                f"no model route for {request.capability.value}; "
                f"rejected={decision.rejected_reason_codes}"
            )
        last_error: BaseException | None = None
        for fallback_index, candidate in enumerate(decision.candidates):
            if candidate.model.paid and self.paid_side_effects is None:
                raise PaidSideEffectGuardRequired(
                    PaidSideEffectGuardRequired.code
                )
            reservation = await self.budget.reserve(request, candidate)
            if not reservation.allowed:
                last_error = ProviderCallError(
                    ErrorCategory.BUDGET_EXCEEDED,
                    reservation.reason or "budget reservation rejected",
                    provider=candidate.model.provider,
                    acceptance=ProviderAcceptance.NOT_ACCEPTED,
                )
                continue
            try:
                result, retries = await self._invoke_candidate(request, candidate)
            except ProviderCallError as exc:
                await self.budget.release(reservation)
                last_error = exc
                self.router.health.record_failure(
                    candidate.model.provider,
                    candidate.model.model,
                    exc.category.value,
                )
                if not self._can_fallback(request, candidate, exc):
                    raise
                continue
            except BaseException:
                await self.budget.release(reservation)
                raise
            await self.budget.settle(reservation, actual=result.cost)
            latency_ms = result.timing.total_ms if result.timing else None
            self.router.health.record_success(
                candidate.model.provider,
                candidate.model.model,
                latency_ms,
            )
            await self.telemetry.record(
                CostTelemetry(
                    request=request,
                    candidate=candidate,
                    result=result,
                    fallback_index=fallback_index,
                    retry_count=retries,
                )
            )
            return result
        if last_error is not None:
            raise last_error
        raise NoRouteAvailable("all routes were filtered or budget rejected")

    async def stream(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelStreamChunk]:
        decision = self.router.route(request)
        if not decision.candidates:
            raise NoRouteAvailable(
                f"no stream route for {request.capability.value}"
            )
        candidate = decision.candidates[0]
        if candidate.model.paid:
            raise PaidSideEffectGuardRequired(
                "paid streaming requires a streaming-aware NODE-20 checkpoint adapter; "
                "v1 fails closed"
            )
        reservation = await self.budget.reserve(request, candidate)
        if not reservation.allowed:
            raise ProviderCallError(
                ErrorCategory.BUDGET_EXCEEDED,
                reservation.reason or "budget rejected",
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
            )
        adapter = self.registry.adapter(candidate.model.provider)
        try:
            async for chunk in adapter.stream(request, candidate.model):
                yield chunk
        except BaseException:
            await self.budget.release(reservation)
            raise
        await self.budget.settle(reservation, actual=candidate.estimate)

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> NormalizedResult:
        adapter = self.registry.adapter(provider)
        target = self.registry.model(provider, model)
        return await adapter.get_async_status(provider_request_id, target)

    async def cancel(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> bool:
        adapter = self.registry.adapter(provider)
        target = self.registry.model(provider, model)
        return await adapter.cancel(provider_request_id, target)

    async def _invoke_candidate(
        self,
        request: ModelRequest,
        candidate: RouteCandidate,
    ) -> tuple[NormalizedResult, int]:
        adapter = self.registry.adapter(candidate.model.provider)

        async def call_once() -> NormalizedResult:
            if candidate.model.paid:
                assert self.paid_side_effects is not None
                return await self.paid_side_effects.execute(
                    request=request,
                    candidate=candidate,
                    effect=lambda: adapter.invoke(request, candidate.model),
                    reconcile=lambda provider_request_id: adapter.get_async_status(
                        provider_request_id,
                        candidate.model,
                    ),
                )
            return await adapter.invoke(request, candidate.model)

        started = monotonic()
        last: ProviderCallError | None = None
        for attempt in range(self.retry_policy.max_attempts_per_provider):
            try:
                result = await call_once()
                return result, attempt
            except ProviderCallError as exc:
                last = exc
                if (
                    candidate.model.paid
                    and exc.acceptance is not ProviderAcceptance.NOT_ACCEPTED
                ):
                    raise
                if (
                    not exc.retryable
                    or attempt + 1
                    >= self.retry_policy.max_attempts_per_provider
                ):
                    raise
                elapsed = monotonic() - started
                if elapsed >= self.retry_policy.max_elapsed_seconds:
                    raise
                delay = exc.retry_after_seconds
                if delay is None:
                    exponential = min(
                        self.retry_policy.max_delay_seconds,
                        self.retry_policy.base_delay_seconds * (2**attempt),
                    )
                    delay = self.random.uniform(0, exponential)
                remaining = self.retry_policy.max_elapsed_seconds - elapsed
                await self.sleep(min(delay, max(0.0, remaining)))
        assert last is not None
        raise last

    @staticmethod
    def _can_fallback(
        request: ModelRequest,
        candidate: RouteCandidate,
        error: ProviderCallError,
    ) -> bool:
        if (
            not request.routing_hints.allow_fallback
            or error.category not in FALLBACK_ALLOWED
        ):
            return False
        if (
            candidate.model.paid
            and error.acceptance is not ProviderAcceptance.NOT_ACCEPTED
        ):
            return False
        return True
