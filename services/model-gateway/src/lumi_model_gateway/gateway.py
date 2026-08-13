from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .budget import RequestBudgetGuard
from .errors import (
    AmbiguousProviderOutcomeError,
    DeliveryState,
    ModelGatewayError,
    NoRouteError,
    PaidInvocationGuardRequiredError,
    ProviderInvocationError,
)
from .models import (
    CostEstimate,
    ModelRequest,
    ModelResult,
    ResultStatus,
    RouteCandidate,
    StreamChunk,
    TelemetryEvent,
    Usage,
)
from .ports import (
    BudgetGuard,
    CostTelemetrySink,
    PaidInvocationGuard,
    PaidStreamGuard,
    ProviderHealthRegistry,
    ProviderRegistry,
    Sleeper,
)
from .routing import ModelRouter
from .telemetry import NullCostTelemetrySink


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts_per_provider: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0
    max_elapsed_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts_per_provider <= 8:
            raise ValueError("MODEL_RETRY_ATTEMPTS_INVALID")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("MODEL_RETRY_DELAY_INVALID")
        if self.max_elapsed_seconds <= 0:
            raise ValueError("MODEL_RETRY_ELAPSED_INVALID")

    def delay(self, *, retry_index: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return max(0.0, min(retry_after, self.max_delay_seconds))
        exponential = self.base_delay_seconds * (2**retry_index)
        return min(exponential, self.max_delay_seconds)


class AsyncioSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ModelGateway:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        health: ProviderHealthRegistry,
        router: ModelRouter,
        paid_guard: PaidInvocationGuard | None,
        paid_stream_guard: PaidStreamGuard | None = None,
        budget_guard: BudgetGuard | None = None,
        telemetry: CostTelemetrySink | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        if paid_guard is None:
            raise PaidInvocationGuardRequiredError(
                "ModelGateway requires a NODE-20-compatible paid invocation guard"
            )
        self.registry = registry
        self.health = health
        self.router = router
        self.paid_guard = paid_guard
        self.paid_stream_guard = paid_stream_guard
        self.budget_guard = budget_guard or RequestBudgetGuard()
        self.telemetry = telemetry or NullCostTelemetrySink()
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleeper = sleeper or AsyncioSleeper()

    async def invoke(self, request: ModelRequest) -> ModelResult:
        decision = await self.router.route(request)
        candidates = list(decision.candidates)
        if request.routing_hints.get("allow_fallback") is False:
            candidates = candidates[:1]
        last_error: ProviderInvocationError | None = None
        for fallback_index, candidate in enumerate(candidates):
            adapter = self.registry.get(candidate.provider, candidate.model)
            reservation = await self.budget_guard.reserve(
                request=request,
                provider=candidate.provider,
                model=candidate.model,
                estimate=candidate.estimate,
            )
            started = time.monotonic()
            retries = 0
            for provider_attempt in range(self.retry_policy.max_attempts_per_provider):
                attempt_started = time.monotonic()
                try:
                    result = await self.paid_guard.execute(
                        request=request,
                        provider=candidate.provider,
                        model=candidate.model,
                        invoke=lambda: adapter.invoke(request),
                    )
                    self._validate_result(candidate.provider, candidate.model, result)
                except ModelGatewayError as exc:
                    if not isinstance(exc, ProviderInvocationError):
                        await reservation.release()
                        raise
                    error = exc
                except Exception as exc:
                    error = adapter.normalize_error(exc)
                else:
                    self.health.record_success(candidate.provider, candidate.model)
                    await reservation.commit(result.cost)
                    self._record_telemetry(
                        request=request,
                        candidate=candidate,
                        attempt=provider_attempt + 1,
                        fallback_index=fallback_index,
                        retry_count=retries,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        usage=result.usage,
                        cost=result.cost,
                        error_category=None,
                    )
                    return result

                self._record_telemetry(
                    request=request,
                    candidate=candidate,
                    attempt=provider_attempt + 1,
                    fallback_index=fallback_index,
                    retry_count=retries,
                    latency_ms=int((time.monotonic() - attempt_started) * 1000),
                    usage=None,
                    cost=candidate.estimate,
                    error_category=error.category.value,
                )
                last_error = error
                can_retry = (
                    error.retryable
                    and error.delivery_state == DeliveryState.NOT_ACCEPTED
                    and provider_attempt + 1 < self.retry_policy.max_attempts_per_provider
                    and time.monotonic() - started < self.retry_policy.max_elapsed_seconds
                )
                if can_retry:
                    delay = self.retry_policy.delay(
                        retry_index=retries,
                        retry_after=error.retry_after_seconds,
                    )
                    elapsed = time.monotonic() - started
                    if elapsed + delay > self.retry_policy.max_elapsed_seconds:
                        can_retry = False
                    else:
                        retries += 1
                        await self.sleeper.sleep(delay)
                if can_retry:
                    continue
                self.health.record_failure(candidate.provider, candidate.model, error)
                if error.ambiguous:
                    await reservation.commit(candidate.estimate)
                    raise AmbiguousProviderOutcomeError(
                        "provider outcome is not proven safe to retry or cross-fallback: "
                        f"{candidate.key}/{error.category.value}"
                    ) from error
                await reservation.release()
                if not error.fallbackable:
                    raise error
                break
        if last_error is not None:
            raise last_error
        raise NoRouteError("no model route could be executed")

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        if self.paid_stream_guard is None:
            raise PaidInvocationGuardRequiredError(
                "streaming requires a NODE-20-compatible paid stream guard"
            )
        decision = await self.router.route(request)
        candidates = [
            candidate
            for candidate in decision.candidates
            if self.registry.get(candidate.provider, candidate.model).descriptor.supports_streaming
        ]
        if request.routing_hints.get("allow_fallback") is False:
            candidates = candidates[:1]
        if not candidates:
            raise NoRouteError("no streaming-capable provider route")
        for fallback_index, candidate in enumerate(candidates):
            adapter = self.registry.get(candidate.provider, candidate.model)
            reservation = await self.budget_guard.reserve(
                request=request,
                provider=candidate.provider,
                model=candidate.model,
                estimate=candidate.estimate,
            )
            started = time.monotonic()
            emitted = 0
            final_usage: Usage | None = None
            try:
                stream = self.paid_stream_guard.stream(
                    request=request,
                    provider=candidate.provider,
                    model=candidate.model,
                    open_stream=lambda: adapter.stream(request),
                )
                async for chunk in stream:
                    emitted += 1
                    if chunk.usage is not None:
                        final_usage = chunk.usage
                    yield chunk
            except ProviderInvocationError as error:
                self.health.record_failure(candidate.provider, candidate.model, error)
                self._record_telemetry(
                    request=request,
                    candidate=candidate,
                    attempt=1,
                    fallback_index=fallback_index,
                    retry_count=0,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    usage=final_usage,
                    cost=candidate.estimate,
                    error_category=error.category.value,
                )
                if emitted > 0 or error.ambiguous:
                    await reservation.commit(candidate.estimate)
                    raise AmbiguousProviderOutcomeError(
                        "stream failed after provider acceptance/output; fallback is unsafe"
                    ) from error
                await reservation.release()
                if error.fallbackable:
                    continue
                raise
            except Exception as exc:
                error = adapter.normalize_error(exc)
                self.health.record_failure(candidate.provider, candidate.model, error)
                self._record_telemetry(
                    request=request,
                    candidate=candidate,
                    attempt=1,
                    fallback_index=fallback_index,
                    retry_count=0,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    usage=final_usage,
                    cost=candidate.estimate,
                    error_category=error.category.value,
                )
                if emitted > 0 or error.ambiguous:
                    await reservation.commit(candidate.estimate)
                    raise AmbiguousProviderOutcomeError(
                        "stream outcome is ambiguous; fallback is unsafe"
                    ) from error
                await reservation.release()
                if error.fallbackable:
                    continue
                raise error from exc
            else:
                self.health.record_success(candidate.provider, candidate.model)
                await reservation.commit(candidate.estimate)
                self._record_telemetry(
                    request=request,
                    candidate=candidate,
                    attempt=1,
                    fallback_index=fallback_index,
                    retry_count=0,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    usage=final_usage,
                    cost=candidate.estimate,
                    error_category=None,
                )
                return
        raise NoRouteError("all safe streaming fallbacks were exhausted")

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> ModelResult:
        adapter = self.registry.get(provider, model)
        return await adapter.get_async_status(provider_request_id)

    async def cancel(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> ModelResult:
        adapter = self.registry.get(provider, model)
        return await adapter.cancel(provider_request_id)

    def _validate_result(
        self,
        provider: str,
        model: str,
        result: ModelResult,
    ) -> None:
        if result.provider != provider or result.model != model:
            raise RuntimeError("MODEL_PROVIDER_RESULT_IDENTITY_MISMATCH")
        if result.status == ResultStatus.FAILED:
            raise RuntimeError("MODEL_PROVIDER_RETURNED_FAILED_RESULT_WITHOUT_ERROR")

    def _record_telemetry(
        self,
        *,
        request: ModelRequest,
        candidate: RouteCandidate,
        attempt: int,
        fallback_index: int,
        retry_count: int,
        latency_ms: int,
        usage: Usage | None,
        cost: CostEstimate | None,
        error_category: str | None,
    ) -> None:
        self.telemetry.record(
            TelemetryEvent(
                request_id=request.request_id,
                organization_id=request.organization_id,
                operation_id=request.operation_id,
                capability=request.capability,
                provider=candidate.provider,
                model=candidate.model,
                routing_reason_codes=candidate.reason_codes,
                attempt=attempt,
                fallback_index=fallback_index,
                retry_count=retry_count,
                latency_ms=latency_ms,
                usage=usage,
                cost=cost,
                error_category=error_category,
                semantic_hash=request.semantic_hash,
                trace_id=request.trace_id,
            )
        )
