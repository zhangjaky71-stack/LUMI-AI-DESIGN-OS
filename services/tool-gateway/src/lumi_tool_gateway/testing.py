from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .contracts import (
    ApprovalDecision,
    ToolAdapterOutput,
    ToolApproval,
    ToolDefinition,
    ToolRequest,
    ToolSideEffectContext,
    ToolSideEffectResponse,
)


class MemoryResultOffloader:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def store(
        self,
        *,
        organization_id: str,
        tool_call_id: str,
        resolved_tool: str,
        payload: bytes,
    ) -> str:
        digest = hashlib.sha256(payload).hexdigest()
        ref = f"tool-result://{organization_id}/{tool_call_id}/{digest}"
        self.objects[ref] = bytes(payload)
        return ref


class MemoryIdempotentSideEffectGuard:
    """Deterministic test double mirroring NODE-20 replay semantics."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str, str], ToolSideEffectResponse] = {}
        self.invocations = 0
        self.replays = 0

    async def execute(
        self,
        context: ToolSideEffectContext,
        invoke: Callable[[], Awaitable[ToolAdapterOutput]],
    ) -> ToolSideEffectResponse:
        key = (
            str(context.organization_id),
            context.operation_type,
            context.idempotency_key,
        )
        existing = self._results.get(key)
        if existing is not None:
            self.replays += 1
            return ToolSideEffectResponse(
                output=existing.output,
                replayed=True,
                operation_id=existing.operation_id,
            )
        self.invocations += 1
        output = await invoke()
        response = ToolSideEffectResponse(
            output=output,
            replayed=False,
            operation_id=f"test-op-{self.invocations}",
        )
        self._results[key] = response
        return response


@dataclass(slots=True)
class StaticApprovalResolver:
    decision: ApprovalDecision
    approval_id: str = "approval-test-1"
    reason_code: str = "TEST_APPROVAL"

    async def resolve(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolApproval:
        del definition, request
        return ToolApproval(
            self.decision,
            approval_id=self.approval_id,
            reason_code=self.reason_code,
        )


class CountingAdapter:
    def __init__(self, output: ToolAdapterOutput) -> None:
        self.output = output
        self.calls = 0

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        del definition, request
        self.calls += 1
        return self.output
