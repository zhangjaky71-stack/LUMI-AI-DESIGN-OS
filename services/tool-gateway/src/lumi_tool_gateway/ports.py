from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from .audit import ToolAuditRecord
from .contracts import (
    ToolAdapterOutput,
    ToolApproval,
    ToolDefinition,
    ToolRequest,
    ToolSideEffectContext,
    ToolSideEffectResponse,
)


class ToolAdapter(Protocol):
    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput: ...


class ApprovalResolver(Protocol):
    async def resolve(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolApproval: ...


class SideEffectGuard(Protocol):
    async def execute(
        self,
        context: ToolSideEffectContext,
        invoke: Callable[[], Awaitable[ToolAdapterOutput]],
    ) -> ToolSideEffectResponse: ...


class ResultOffloader(Protocol):
    async def store(
        self,
        *,
        organization_id: str,
        tool_call_id: str,
        resolved_tool: str,
        payload: bytes,
    ) -> str: ...


class AuditSink(Protocol):
    def record(self, event: ToolAuditRecord) -> None: ...
