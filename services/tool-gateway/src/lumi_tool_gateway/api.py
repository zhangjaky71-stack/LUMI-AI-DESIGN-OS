from __future__ import annotations

from .contracts import ToolRequest, ToolResult
from .gateway import ToolGateway


class ToolGatewayAPI:
    """Transport-neutral application boundary around ToolGateway."""

    def __init__(self, gateway: ToolGateway) -> None:
        self._gateway = gateway

    async def invoke(self, request: ToolRequest) -> ToolResult:
        return await self._gateway.invoke(request)
