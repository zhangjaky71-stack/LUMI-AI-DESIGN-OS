from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .contracts import (
    CheckpointPointer,
    GraphDefinition,
    GraphInterrupt,
    GraphRunEvent,
    GraphRunRequest,
    GraphRunSnapshot,
    GraphRunStatus,
    ResumeAuthorization,
    ResumeRequest,
)
from .durable_executor import ThreadGraphBinding
from .errors import GraphCheckpointConflictError, GraphRunConflictError, GraphRunNotFoundError


class MemoryGraphRunStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, GraphRunSnapshot] = {}
        self.bindings: dict[str, ThreadGraphBinding] = {}

    async def bind_start(
        self,
        request: GraphRunRequest,
        definition: GraphDefinition,
    ) -> GraphRunSnapshot | None:
        existing = self.runs.get(request.agent_run_id)
        if existing is not None:
            if (
                existing.organization_id != request.organization_id
                or existing.project_id != request.project_id
                or existing.thread_id != request.thread_id
                or existing.graph_key != definition.graph_key
                or existing.graph_version != definition.graph_version
                or existing.agent_config_version != definition.agent_config_version
            ):
                raise GraphRunConflictError("memory start binding mismatch")
            return existing
        self.bindings[request.thread_id] = ThreadGraphBinding(
            thread_id=request.thread_id,
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            task_id=request.task_id,
        )
        return None

    async def persist_snapshot(
        self,
        snapshot: GraphRunSnapshot,
        *,
        expected_checkpoint: CheckpointPointer | None,
    ) -> None:
        existing = self.runs.get(snapshot.agent_run_id)
        if expected_checkpoint is not None:
            if existing is None:
                raise GraphCheckpointConflictError("expected existing checkpoint")
            if (
                existing.thread_id != expected_checkpoint.thread_id
                or existing.checkpoint_namespace != expected_checkpoint.checkpoint_namespace
                or existing.checkpoint_id != expected_checkpoint.checkpoint_id
            ):
                raise GraphCheckpointConflictError("checkpoint CAS mismatch")
        self.runs[snapshot.agent_run_id] = snapshot
        self.bindings[snapshot.thread_id] = ThreadGraphBinding(
            thread_id=snapshot.thread_id,
            graph_key=snapshot.graph_key,
            graph_version=snapshot.graph_version,
            agent_config_version=snapshot.agent_config_version,
            task_id=snapshot.task_id,
        )

    async def load(self, agent_run_id: UUID) -> GraphRunSnapshot | None:
        return self.runs.get(agent_run_id)

    async def resolve_thread(self, thread_id: str) -> ThreadGraphBinding:
        try:
            return self.bindings[thread_id]
        except KeyError as exc:
            raise GraphRunNotFoundError(thread_id) from exc


class MemoryEventSink:
    def __init__(self) -> None:
        self.events: list[GraphRunEvent] = []

    async def publish(self, event: GraphRunEvent) -> None:
        self.events.append(event)


class MemoryOperationGuard:
    def __init__(self) -> None:
        self.results: dict[tuple[UUID, str], tuple[str, GraphRunSnapshot]] = {}
        self.invocations = 0

    async def execute(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        operation_type: str,
        request_hash: str,
        invoke,
    ) -> GraphRunSnapshot:
        key = (operation_id, operation_type)
        existing = self.results.get(key)
        if existing is not None:
            old_hash, result = existing
            if old_hash != request_hash:
                raise GraphRunConflictError("operation replay hash mismatch")
            return result
        self.invocations += 1
        result = await invoke()
        self.results[key] = (request_hash, result)
        return result


class StaticResumeAuthorizer:
    def __init__(
        self,
        *,
        authorized: bool = True,
        normalized_value: Any = None,
    ) -> None:
        self.authorized = authorized
        self.normalized_value = normalized_value
        self.calls: list[str] = []

    async def authorize(
        self,
        request: ResumeRequest,
        *,
        current: GraphRunSnapshot,
    ) -> ResumeAuthorization:
        self.calls.append(request.interrupt_id)
        return ResumeAuthorization(
            approval_id=None,
            approved=self.authorized,
            bound_interrupt_id=request.interrupt_id,
            normalized_value=self.normalized_value,
            reason=None if self.authorized else "denied by test policy",
        )


class ScriptedGraphExecutor:
    def __init__(self, snapshots: list[GraphRunSnapshot]) -> None:
        self.snapshots = list(snapshots)
        self.start_calls = 0
        self.resume_calls = 0
        self.cancel_calls = 0
        self.resume_values: list[Any] = []

    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot:
        self.start_calls += 1
        return self._next()

    async def resume(
        self,
        request: ResumeRequest,
        *,
        normalized_value: Any,
    ) -> GraphRunSnapshot:
        self.resume_calls += 1
        self.resume_values.append(normalized_value)
        return self._next()

    async def snapshot(
        self,
        *,
        definition: GraphDefinition,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        task_id: UUID | None,
        thread_id: str,
    ) -> GraphRunSnapshot:
        del definition, organization_id, project_id, agent_run_id, task_id, thread_id
        if not self.snapshots:
            raise GraphRunConflictError("no scripted snapshot")
        return self.snapshots[0]

    async def cancel(
        self,
        *,
        definition: GraphDefinition,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        thread_id: str,
    ) -> GraphRunSnapshot:
        del definition, organization_id, project_id, agent_run_id, thread_id
        self.cancel_calls += 1
        current = self._next()
        return replace(
            current,
            status=GraphRunStatus.CANCELLED,
            interrupts=(),
            next_nodes=(),
            updated_at=datetime.now(UTC),
        )

    def _next(self) -> GraphRunSnapshot:
        if not self.snapshots:
            raise GraphRunConflictError("scripted executor exhausted")
        return self.snapshots.pop(0)


def snapshot(
    *,
    definition: GraphDefinition,
    request: GraphRunRequest,
    status: GraphRunStatus,
    checkpoint_id: str,
    interrupts: tuple[GraphInterrupt, ...] = (),
    next_nodes: tuple[str, ...] = (),
    state_values: dict[str, Any] | None = None,
) -> GraphRunSnapshot:
    now = datetime.now(UTC)
    return GraphRunSnapshot(
        organization_id=request.organization_id,
        project_id=request.project_id,
        agent_run_id=request.agent_run_id,
        task_id=request.task_id,
        thread_id=request.thread_id,
        graph_key=definition.graph_key,
        graph_version=definition.graph_version,
        agent_config_version=definition.agent_config_version,
        status=status,
        checkpoint_id=checkpoint_id,
        checkpoint_namespace="",
        state_values=state_values or {},
        next_nodes=next_nodes,
        interrupts=interrupts,
        created_at=now,
        updated_at=now,
    )


def fake_interrupt(*, interrupt_id: str = "interrupt-1") -> GraphInterrupt:
    return GraphInterrupt(
        interrupt_id=interrupt_id,
        kind="approval",  # type: ignore[arg-type]
        namespace=("review",),
        node_name="review",
        payload={"approval_id": "00000000-0000-0000-0000-000000000001"},
        resumable=True,
    )


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
