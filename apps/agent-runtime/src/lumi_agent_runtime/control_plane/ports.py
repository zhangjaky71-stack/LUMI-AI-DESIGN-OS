from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from .contracts import (
    CheckpointPointer,
    GraphDefinition,
    GraphRunEvent,
    GraphRunRequest,
    GraphRunSnapshot,
    ResumeAuthorization,
    ResumeRequest,
)


class GraphExecutor(Protocol):
    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot: ...

    async def resume(
        self,
        request: ResumeRequest,
        *,
        normalized_value: Any,
    ) -> GraphRunSnapshot: ...

    async def snapshot(
        self,
        *,
        definition: GraphDefinition,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        task_id: UUID | None,
        thread_id: str,
    ) -> GraphRunSnapshot: ...

    async def cancel(
        self,
        *,
        definition: GraphDefinition,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        thread_id: str,
    ) -> GraphRunSnapshot: ...


class GraphRunStore(Protocol):
    async def bind_start(
        self,
        request: GraphRunRequest,
        definition: GraphDefinition,
    ) -> GraphRunSnapshot | None: ...

    async def persist_snapshot(
        self,
        snapshot: GraphRunSnapshot,
        *,
        expected_checkpoint: CheckpointPointer | None,
    ) -> None: ...

    async def load(self, agent_run_id: UUID) -> GraphRunSnapshot | None: ...


class ResumeAuthorizer(Protocol):
    async def authorize(
        self,
        request: ResumeRequest,
        *,
        current: GraphRunSnapshot,
    ) -> ResumeAuthorization: ...


class GraphEventSink(Protocol):
    async def publish(self, event: GraphRunEvent) -> None: ...


class ControlPlaneOperationGuard(Protocol):
    async def execute(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        operation_type: str,
        request_hash: str,
        invoke: Callable[[], Awaitable[GraphRunSnapshot]],
    ) -> GraphRunSnapshot: ...
