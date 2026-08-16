from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from .errors import (
    FALLBACK_ALLOWED,
    ErrorCategory,
    ModelCapabilityTemporarilyUnavailable,
    NoRouteAvailable,
    PaidSideEffectGuardRequired,
    ProviderAcceptance,
    ProviderCallError,
)
from .models import (
    Capability,
    ModelRequest,
    ModelStreamChunk,
    ModelTiming,
    ModelUsage,
    NormalizedResult,
    ResultStatus,
    RouteCandidate,
)
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
            raise ValueError(
                "max_attempts_per_provider must be >= 1"
            )


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

    async def invoke(
        self,
        request: ModelRequest,
    ) -> NormalizedResult:
        decision = self.router.route(request)
        if not decision.candidates:
            self._raise_no_route(
                request,
                decision.rejected_reason_codes,
            )
        last_error: BaseException | None = None
        health_gate_rejected = 0
        candidates = decision.candidates
        for fallback_index, candidate in enumerate(candidates):
            if candidate.model.paid and self.paid_side_effects is None:
                raise PaidSideEffectGuardRequired(
                    PaidSideEffectGuardRequired.code
                )
            reservation = await self.budget.reserve(
                request,
                candidate,
            )
            if not reservation.allowed:
                last_error = ProviderCallError(
                    ErrorCategory.BUDGET_EXCEEDED,
                    reservation.reason
                    or "budget reservation rejected",
                    provider=candidate.model.provider,
                    acceptance=ProviderAcceptance.NOT_ACCEPTED,
                )
                self._record_fallback_if_possible(
                    fallback_index,
                    len(candidates),
                )
                continue

            capability = request.capability.value
            if not self.router.health.acquire_probe(
                candidate.model.provider,
                candidate.model.model,
                capability=capability,
            ):
                await self.budget.release(reservation)
                health_gate_rejected += 1
                last_error = ProviderCallError(
                    ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
                    "health recovery probe capacity unavailable",
                    provider=candidate.model.provider,
                    retryable=True,
                    acceptance=ProviderAcceptance.NOT_ACCEPTED,
                )
                self._record_fallback_if_possible(
                    fallback_index,
                    len(candidates),
                )
                continue

            started = monotonic()
            try:
                result, retries = await self._invoke_candidate(
                    request,
                    candidate,
                )
            except ProviderCallError as exc:
                await self.budget.release(reservation)
                last_error = exc
                elapsed_ms = int(
                    (monotonic() - started) * 1000
                )
                self.router.health.record_failure(
                    candidate.model.provider,
                    candidate.model.model,
                    exc.category.value,
                    capability=capability,
                    latency_ms=elapsed_ms,
                    retry_after_seconds=(
                        exc.retry_after_seconds
                    ),
                )
                self.router.health.release_probe(
                    candidate.model.provider,
                    candidate.model.model,
                    capability=capability,
                )
                if not self._can_fallback(
                    request,
                    candidate,
                    exc,
                ):
                    raise
                self._record_fallback_if_possible(
                    fallback_index,
                    len(candidates),
                )
                continue
            except BaseException:
                await self.budget.release(reservation)
                self.router.health.release_probe(
                    candidate.model.provider,
                    candidate.model.model,
                    capability=capability,
                )
                raise

            await self.budget.settle(
                reservation,
                actual=result.cost,
                usage=result.usage,
                provider_request_id=result.provider_request_id,
            )
            latency_ms = (
                result.timing.total_ms
                if result.timing is not None
                else int((monotonic() - started) * 1000)
            )
            self.router.health.record_success(
                candidate.model.provider,
                candidate.model.model,
                latency_ms,
                capability=capability,
            )
            self.router.health.release_probe(
                candidate.model.provider,
                candidate.model.model,
                capability=capability,
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

        if health_gate_rejected == len(candidates):
            self.router.health.record_all_candidates_unavailable()
            raise ModelCapabilityTemporarilyUnavailable(
                ModelCapabilityTemporarilyUnavailable.code
            )
        if last_error is not None:
            raise last_error
        raise NoRouteAvailable(
            "all routes were filtered or budget rejected"
        )

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamChunk]:
        decision = self.router.route(request)
        if not decision.candidates:
            self._raise_no_route(
                request,
                decision.rejected_reason_codes,
            )
        candidate = decision.candidates[0]
        if candidate.model.paid:
            raise PaidSideEffectGuardRequired(
                "paid streaming requires a streaming-aware NODE-20 "
                "checkpoint adapter; v1 fails closed"
            )
        reservation = await self.budget.reserve(
            request,
            candidate,
        )
        if not reservation.allowed:
            raise ProviderCallError(
                ErrorCategory.BUDGET_EXCEEDED,
                reservation.reason or "budget rejected",
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
            )

        capability = request.capability.value
        if not self.router.health.acquire_probe(
            candidate.model.provider,
            candidate.model.model,
            capability=capability,
        ):
            await self.budget.release(reservation)
            self.router.health.record_all_candidates_unavailable()
            raise ModelCapabilityTemporarilyUnavailable(
                ModelCapabilityTemporarilyUnavailable.code
            )

        adapter = self.registry.adapter(
            candidate.model.provider
        )
        started = monotonic()
        usage = ModelUsage()
        provider_request_id: str | None = None
        finish_reason: str | None = None
        try:
            async for chunk in adapter.stream(
                request,
                candidate.model,
            ):
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.provider_request_id:
                    provider_request_id = (
                        chunk.provider_request_id
                    )
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                yield chunk
        except ProviderCallError as exc:
            await self.budget.release(reservation)
            elapsed_ms = int(
                (monotonic() - started) * 1000
            )
            self.router.health.record_failure(
                candidate.model.provider,
                candidate.model.model,
                exc.category.value,
                capability=capability,
                latency_ms=elapsed_ms,
                retry_after_seconds=exc.retry_after_seconds,
            )
            self.router.health.release_probe(
                candidate.model.provider,
                candidate.model.model,
                capability=capability,
            )
            raise
        except BaseException:
            await self.budget.release(reservation)
            self.router.health.release_probe(
                candidate.model.provider,
                candidate.model.model,
                capability=capability,
            )
            raise

        timing = ModelTiming(
            total_ms=int((monotonic() - started) * 1000)
        )
        result = NormalizedResult(
            status=ResultStatus.COMPLETED,
            provider=candidate.model.provider,
            model=candidate.model.model,
            provider_request_id=provider_request_id,
            usage=usage,
            timing=timing,
            finish_reason=finish_reason,
            cost=candidate.estimate,
        )
        await self.budget.settle(
            reservation,
            actual=result.cost,
            usage=usage,
            provider_request_id=provider_request_id,
        )
        self.router.health.record_success(
            candidate.model.provider,
            candidate.model.model,
            timing.total_ms,
            capability=capability,
        )
        self.router.health.release_probe(
            candidate.model.provider,
            candidate.model.model,
            capability=capability,
        )
        await self.telemetry.record(
            CostTelemetry(
                request=request,
                candidate=candidate,
                result=result,
                fallback_index=0,
                retry_count=0,
            )
        )

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
        capability: Capability | None = None,
        queue_started_epoch: float | None = None,
    ) -> NormalizedResult:
        adapter = self.registry.adapter(provider)
        target = self.registry.model(provider, model)
        capability_value = (
            None if capability is None else capability.value
        )
        started = monotonic()
        try:
            result = await adapter.get_async_status(
                provider_request_id,
                target,
            )
        except ProviderCallError as exc:
            self.router.health.record_failure(
                provider,
                model,
                exc.category.value,
                capability=capability_value,
                latency_ms=int(
                    (monotonic() - started) * 1000
                ),
                retry_after_seconds=exc.retry_after_seconds,
            )
            raise
        if (
            result.status is ResultStatus.COMPLETED
            and queue_started_epoch is not None
        ):
            completion_ms = max(
                0,
                int(
                    (time.time() - queue_started_epoch)
                    * 1000
                ),
            )
            self.router.health.record_queue_completion(
                provider,
                model,
                completion_ms,
                capability=capability_value,
            )
        return result

    async def cancel(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> bool:
        adapter = self.registry.adapter(provider)
        target = self.registry.model(provider, model)
        return await adapter.cancel(
            provider_request_id,
            target,
        )

    async def _invoke_candidate(
        self,
        request: ModelRequest,
        candidate: RouteCandidate,
    ) -> tuple[NormalizedResult, int]:
        adapter = self.registry.adapter(
            candidate.model.provider
        )

        async def call_once() -> NormalizedResult:
            if candidate.model.paid:
                assert self.paid_side_effects is not None
                return await self.paid_side_effects.execute(
                    request=request,
                    candidate=candidate,
                    effect=lambda: adapter.invoke(
                        request,
                        candidate.model,
                    ),
                    reconcile=(
                        lambda provider_request_id: (
                            adapter.get_async_status(
                                provider_request_id,
                                candidate.model,
                            )
                        )
                    ),
                )
            return await adapter.invoke(
                request,
                candidate.model,
            )

        started = monotonic()
        last: ProviderCallError | None = None
        for attempt in range(
            self.retry_policy.max_attempts_per_provider
        ):
            try:
                result = await call_once()
                return result, attempt
            except ProviderCallError as exc:
                last = exc
                if (
                    candidate.model.paid
                    and exc.acceptance
                    is not ProviderAcceptance.NOT_ACCEPTED
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
                        self.retry_policy.base_delay_seconds
                        * (2**attempt),
                    )
                    delay = self.random.uniform(
                        0,
                        exponential,
                    )
                remaining = (
                    self.retry_policy.max_elapsed_seconds
                    - elapsed
                )
                await self.sleep(
                    min(
                        delay,
                        max(0.0, remaining),
                    )
                )
        assert last is not None
        raise last

    def _raise_no_route(
        self,
        request: ModelRequest,
        rejected_reason_codes: tuple[str, ...],
    ) -> None:
        if any(
            reason.endswith(":health_filtered")
            for reason in rejected_reason_codes
        ):
            self.router.health.record_all_candidates_unavailable()
            raise ModelCapabilityTemporarilyUnavailable(
                f"{ModelCapabilityTemporarilyUnavailable.code}: "
                f"{request.capability.value}"
            )
        raise NoRouteAvailable(
            f"no model route for {request.capability.value}; "
            f"rejected={rejected_reason_codes}"
        )

    def _record_fallback_if_possible(
        self,
        fallback_index: int,
        candidate_count: int,
    ) -> None:
        if fallback_index + 1 < candidate_count:
            self.router.health.record_fallback()

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
            and error.acceptance
            is not ProviderAcceptance.NOT_ACCEPTED
        ):
            return False
        return True
