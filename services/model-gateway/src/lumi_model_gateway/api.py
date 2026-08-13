from __future__ import annotations

from collections.abc import AsyncIterator

from .gateway import ModelGateway
from .models import ModelRequest, ModelResult, StreamChunk


class ModelGatewayAPI:
    """Provider-neutral application API. HTTP/RPC transports can wrap this facade."""

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def invoke(self, request: ModelRequest) -> ModelResult:
        return await self.gateway.invoke(request)

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        async for chunk in self.gateway.stream(request):
            yield chunk

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> ModelResult:
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
    ) -> ModelResult:
        return await self.gateway.cancel(
            provider=provider,
            model=model,
            provider_request_id=provider_request_id,
        )
