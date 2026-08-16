from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .gateway import ModelGateway
from .models import ModelRequest, ModelStreamChunk, NormalizedResult


class ModelGatewayClient(Protocol):
    async def invoke(self, request: ModelRequest) -> NormalizedResult: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]: ...

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> NormalizedResult: ...

    async def cancel(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> bool: ...


class InProcessModelGatewayClient:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def invoke(self, request: ModelRequest) -> NormalizedResult:
        return await self.gateway.invoke(request)

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]:
        return self.gateway.stream(request)

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> NormalizedResult:
        return await self.gateway.get_async_status(
            provider=provider,
            model=model,
            provider_request_id=provider_request_id,
        )

    async def cancel(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> bool:
        return await self.gateway.cancel(
            provider=provider,
            model=model,
            provider_request_id=provider_request_id,
        )
