from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from .errors import ProviderInvocationError
from .models import (
    CostEstimate,
    ModelRequest,
    ModelResult,
    ProviderModel,
    StreamChunk,
    TelemetryEvent,
    Usage,
)


class ProviderAdapter(Protocol):
    @property
    def descriptor(self) -> ProviderModel: ...

    def validate(self, request: ModelRequest) -> None: ...

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate: ...

    async def invoke(self, request: ModelRequest) -> ModelResult: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]: ...

    async def get_async_status(self, provider_request_id: str) -> ModelResult: ...

    async def cancel(self, provider_request_id: str) -> ModelResult: ...

    def normalize_error(self, error: Exception) -> ProviderInvocationError: ...


class ProviderRegistry(Protocol):
    def adapters(self) -> tuple[ProviderAdapter, ...]: ...

    def get(self, provider: str, model: str) -> ProviderAdapter: ...


class ProviderHealthRegistry(Protocol):
    def healthy(self, provider: str, model: str) -> bool: ...

    def record_success(self, provider: str, model: str) -> None: ...

    def record_failure(
        self,
        provider: str,
        model: str,
        error: ProviderInvocationError,
    ) -> None: ...


class CostTelemetrySink(Protocol):
    def record(self, event: TelemetryEvent) -> None: ...


class PaidInvocationGuard(Protocol):
    async def execute(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        invoke: Callable[[], Awaitable[ModelResult]],
    ) -> ModelResult: ...


class PaidStreamGuard(Protocol):
    def stream(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        open_stream: Callable[[], AsyncIterator[StreamChunk]],
    ) -> AsyncIterator[StreamChunk]: ...


class BudgetReservation(Protocol):
    async def commit(
        self,
        actual: CostEstimate,
        *,
        usage: Usage | None = None,
        provider_request_id: str | None = None,
    ) -> None: ...

    async def release(self, *, reason: str = "not_accepted") -> None: ...


class BudgetGuard(Protocol):
    async def reserve(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        estimate: CostEstimate,
    ) -> BudgetReservation: ...


class Sleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...
