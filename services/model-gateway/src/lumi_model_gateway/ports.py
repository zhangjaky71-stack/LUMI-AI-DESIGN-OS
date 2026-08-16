from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .errors import ProviderCallError
from .models import (
    CostEstimate,
    HealthSnapshot,
    ModelRequest,
    ModelStreamChunk,
    NormalizedResult,
    ProviderModel,
    RouteCandidate,
)


class ProviderAdapter(Protocol):
    @property
    def provider_name(self) -> str: ...

    def models(self) -> tuple[ProviderModel, ...]: ...

    def validate(self, request: ModelRequest, model: ProviderModel) -> None: ...

    def estimate_cost(self, request: ModelRequest, model: ProviderModel) -> CostEstimate: ...

    async def invoke(self, request: ModelRequest, model: ProviderModel) -> NormalizedResult: ...

    async def stream(
        self, request: ModelRequest, model: ProviderModel
    ) -> AsyncIterator[ModelStreamChunk]: ...

    async def get_async_status(self, provider_request_id: str, model: ProviderModel) -> NormalizedResult: ...

    async def cancel(self, provider_request_id: str, model: ProviderModel) -> bool: ...

    def normalize_error(self, error: BaseException) -> ProviderCallError: ...


class SecretProvider(Protocol):
    def get_secret(self, provider: str, name: str) -> str: ...


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    allowed: bool
    reservation_ref: str | None = None
    remaining_usd: Decimal | None = None
    reason: str | None = None


class BudgetPort(Protocol):
    async def reserve(
        self,
        request: ModelRequest,
        candidate: RouteCandidate,
    ) -> BudgetReservation: ...

    async def settle(
        self,
        reservation: BudgetReservation,
        *,
        actual: CostEstimate,
    ) -> None: ...

    async def release(self, reservation: BudgetReservation) -> None: ...


@dataclass(frozen=True, slots=True)
class CostTelemetry:
    request: ModelRequest
    candidate: RouteCandidate
    result: NormalizedResult
    fallback_index: int
    retry_count: int


class CostTelemetryPort(Protocol):
    async def record(self, telemetry: CostTelemetry) -> None: ...


class HealthPort(Protocol):
    def snapshot(self, provider: str, model: str) -> HealthSnapshot: ...

    def record_success(self, provider: str, model: str, latency_ms: int | None) -> None: ...

    def record_failure(self, provider: str, model: str, category: str) -> None: ...


PaidEffect = Callable[[], Awaitable[NormalizedResult]]
ReconcileEffect = Callable[[str], Awaitable[NormalizedResult]]


class PaidSideEffectPort(Protocol):
    async def execute(
        self,
        *,
        request: ModelRequest,
        candidate: RouteCandidate,
        effect: PaidEffect,
        reconcile: ReconcileEffect | None = None,
    ) -> NormalizedResult: ...


class SleepPort(Protocol):
    async def __call__(self, seconds: float) -> None: ...
