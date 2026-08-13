from __future__ import annotations

from collections.abc import AsyncIterator

from .api import ModelGatewayAPI
from .models import ModelRequest, ModelResult, StreamChunk


class ModelGatewayClient:
    """Caller-facing client contract that exposes no provider adapter/native schema."""

    def __init__(self, api: ModelGatewayAPI) -> None:
        self._api = api

    async def invoke(self, request: ModelRequest) -> ModelResult:
        return await self._api.invoke(request)

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        async for chunk in self._api.stream(request):
            yield chunk

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> ModelResult:
        return await self._api.get_async_status(
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
        return await self._api.cancel(
            provider=provider,
            model=model,
            provider_request_id=provider_request_id,
        )
