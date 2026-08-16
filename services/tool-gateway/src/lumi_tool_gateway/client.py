from __future__ import annotations

from typing import Protocol

from .contracts import ToolRequest, ToolResult


class ToolGatewayTransport(Protocol):
    async def invoke(self, request: ToolRequest) -> ToolResult: ...


class ToolGatewayClient:
    """Narrow Agent-facing client; Registry/Adapters remain server-side."""

    def __init__(self, transport: ToolGatewayTransport) -> None:
        self._transport = transport

    async def invoke(self, request: ToolRequest) -> ToolResult:
        return await self._transport.invoke(request)
