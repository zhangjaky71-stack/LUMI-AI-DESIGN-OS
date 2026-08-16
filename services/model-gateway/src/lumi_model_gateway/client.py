from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .gateway import ModelGateway
from .models import ModelRequest, ModelStreamChunk, NormalizedResult


class ModelGatewayClient(Protocol):
    async def invoke(self, request: ModelRequest) -> NormalizedResult: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]: ...


class InProcessModelGatewayClient:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def invoke(self, request: ModelRequest) -> NormalizedResult:
        return await self.gateway.invoke(request)

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]:
        return self.gateway.stream(request)
