from __future__ import annotations

import hashlib
import json
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
    ResumeRequest,
)
from .errors import (
    GraphInterruptNotFoundError,
    GraphResumeDeniedError,
    GraphRunConflictError,
    GraphRunNotFoundError,
    GraphRunTerminalError,
)
from .ports import (
    ControlPlaneOperationGuard,
    GraphEventSink,
    GraphExecutor,
    GraphRunStore,
    ResumeAuthorizer,
)
from .registry import GraphRegistry

_TERMINAL = {
    GraphRunStatus.SUCCEEDED,
    GraphRunStatus.FAILED,
    GraphRunStatus.CANCELLED,
}


class LangGraphControlPlane:
    """LUMI-owned orchestration boundary around durable LangGraph execution.

    LangGraph owns graph execution/checkpoints. LUMI owns tenant identity, immutable graph
    versions, AgentRun lifecycle, resume authorization, idempotent control commands and
    operational events. The control plane never resumes an interrupt from arbitrary client
    payload without the ``ResumeAuthorizer`` binding it to the current interrupt.
    """

    def __init__(
        self,
        *,
        registry: GraphRegistry,
        executor: GraphExecutor,
        store: GraphRunStore,
        resume_authorizer: ResumeAuthorizer,
        operation_guard: ControlPlaneOperationGuard,
        events: GraphEventSink,
    ) -> None:
        self.registry = registry
        self.executor = executor
        self.store = store
        self.resume_authorizer = resume_authorizer
        self.operation_guard = operation_guard
        self.events = events

    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot:
        definition = self.registry.resolve(
            request.graph_key,
            request.graph_version,
            agent_config_version=request.agent_config_version,
            require_enabled=True,
        )
        request_hash = _start_hash(request, definition)

        async def invoke() -> GraphRunSnapshot:
            existing = await self.store.bind_start(request, definition)
            if existing is not None:
                self._assert_same_run(existing, request)
                return existing
            snapshot = await self.executor.start(request)
            self._validate_snapshot(snapshot, request=request, definition=definition)
            await self.store.persist_snapshot(snapshot, expected_checkpoint=None)
            await self._publish("agent_run.started", snapshot, request.trace_id)
            if snapshot.status == GraphRunStatus.INTERRUPTED:
                await self._publish("agent_run.interrupted", snapshot, request.trace_id)
            elif snapshot.status == GraphRunStatus.SUCCEEDED:
                await self._publish("agent_run.succeeded", snapshot, request.trace_id)
            return snapshot

        return await self.operation_guard.execute(
            organization_id=request.organization_id,
            operation_id=request.operation_id,
            operation_type="langgraph.start",
            request_hash=request_hash,
            invoke=invoke,
        )

    async def resume(self, request: ResumeRequest) -> GraphRunSnapshot:
        current = await self.store.load(request.agent_run_id)
        if current is None:
            raise GraphRunNotFoundError(f"AgentRun not found: {request.agent_run_id}")
        self._assert_resume_scope(current, request)
        if current.status in _TERMINAL:
            raise GraphRunTerminalError(f"cannot resume terminal run: {current.status.value}")
        if current.status != GraphRunStatus.INTERRUPTED:
            raise GraphRunConflictError(
                f"run must be interrupted before resume, got {current.status.value}"
            )
        interrupt = _find_interrupt(current.interrupts, request.interrupt_id)
        definition = self.registry.resolve(
            current.graph_key,
            current.graph_version,
            agent_config_version=current.agent_config_version,
            require_enabled=True,
        )
        request_hash = _resume_hash(request, current)

        async def invoke() -> GraphRunSnapshot:
            # Re-read inside the operation guard so a concurrent resume cannot authorize
            # against stale interrupt state.
            fresh = await self.store.load(request.agent_run_id)
            if fresh is None:
                raise GraphRunNotFoundError(f"AgentRun not found: {request.agent_run_id}")
            self._assert_resume_scope(fresh, request)
            if fresh.status in _TERMINAL:
                return fresh
            if fresh.status != GraphRunStatus.INTERRUPTED:
                raise GraphRunConflictError("interrupt already resumed by another operation")
            fresh_interrupt = _find_interrupt(fresh.interrupts, request.interrupt_id)
            authorization = await self.resume_authorizer.authorize(
                request,
                current=fresh,
            )
            # ``approved`` means LUMI authorizes execution of the resume command. A human
            # business decision may itself be REJECTED and still be a legitimate resume
            # value; the normalized value carries that business decision.
            if not authorization.approved:
                raise GraphResumeDeniedError(authorization.reason or "resume not authorized")
            if authorization.bound_interrupt_id != fresh_interrupt.interrupt_id:
                raise GraphResumeDeniedError("resume authorization is bound to another interrupt")
            expected = CheckpointPointer(
                thread_id=fresh.thread_id,
                checkpoint_namespace=fresh.checkpoint_namespace,
                checkpoint_id=fresh.checkpoint_id,
            )
            resumed = await self.executor.resume(
                request,
                normalized_value=authorization.normalized_value,
            )
            self._validate_snapshot(
                resumed,
                definition=definition,
                organization_id=fresh.organization_id,
                project_id=fresh.project_id,
                agent_run_id=fresh.agent_run_id,
                task_id=fresh.task_id,
                thread_id=fresh.thread_id,
            )
            await self.store.persist_snapshot(resumed, expected_checkpoint=expected)
            await self._publish("agent_run.resumed", resumed, request.trace_id)
            if resumed.status == GraphRunStatus.INTERRUPTED:
                await self._publish("agent_run.interrupted", resumed, request.trace_id)
            elif resumed.status == GraphRunStatus.SUCCEEDED:
                await self._publish("agent_run.succeeded", resumed, request.trace_id)
            return resumed

        del interrupt
        return await self.operation_guard.execute(
            organization_id=request.organization_id,
            operation_id=request.operation_id,
            operation_type="langgraph.resume",
            request_hash=request_hash,
            invoke=invoke,
        )

    async def snapshot(self, agent_run_id: UUID) -> GraphRunSnapshot:
        current = await self.store.load(agent_run_id)
        if current is None:
            raise GraphRunNotFoundError(f"AgentRun not found: {agent_run_id}")
        definition = self.registry.resolve(
            current.graph_key,
            current.graph_version,
            agent_config_version=current.agent_config_version,
            require_enabled=False,
        )
        snapshot = await self.executor.snapshot(
            definition=definition,
            organization_id=current.organization_id,
            project_id=current.project_id,
            agent_run_id=current.agent_run_id,
            task_id=current.task_id,
            thread_id=current.thread_id,
        )
        self._validate_snapshot(
            snapshot,
            definition=definition,
            organization_id=current.organization_id,
            project_id=current.project_id,
            agent_run_id=current.agent_run_id,
            task_id=current.task_id,
            thread_id=current.thread_id,
        )
        return snapshot

    async def cancel(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        trace_id: str | None = None,
    ) -> GraphRunSnapshot:
        current = await self.store.load(agent_run_id)
        if current is None:
            raise GraphRunNotFoundError(f"AgentRun not found: {agent_run_id}")
        if current.organization_id != organization_id or current.project_id != project_id:
            raise GraphRunNotFoundError("AgentRun not found in tenant/project scope")
        if current.status in _TERMINAL:
            return current
        definition = self.registry.resolve(
            current.graph_key,
            current.graph_version,
            agent_config_version=current.agent_config_version,
            require_enabled=False,
        )
        request_hash = hashlib.sha256(
            f"{organization_id}:{project_id}:{agent_run_id}:{current.thread_id}:cancel".encode()
        ).hexdigest()

        async def invoke() -> GraphRunSnapshot:
            fresh = await self.store.load(agent_run_id)
            if fresh is None:
                raise GraphRunNotFoundError(f"AgentRun not found: {agent_run_id}")
            if fresh.status in _TERMINAL:
                return fresh
            expected = CheckpointPointer(
                thread_id=fresh.thread_id,
                checkpoint_namespace=fresh.checkpoint_namespace,
                checkpoint_id=fresh.checkpoint_id,
            )
            cancelled = await self.executor.cancel(
                definition=definition,
                organization_id=organization_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
                thread_id=fresh.thread_id,
            )
            if cancelled.status != GraphRunStatus.CANCELLED:
                raise GraphRunConflictError("executor did not return cancelled state")
            await self.store.persist_snapshot(cancelled, expected_checkpoint=expected)
            await self._publish("agent_run.cancelled", cancelled, trace_id)
            return cancelled

        return await self.operation_guard.execute(
            organization_id=organization_id,
            operation_id=operation_id,
            operation_type="langgraph.cancel",
            request_hash=request_hash,
            invoke=invoke,
        )

    async def _publish(
        self,
        event_type: str,
        snapshot: GraphRunSnapshot,
        trace_id: str | None,
    ) -> None:
        await self.events.publish(
            GraphRunEvent(
                event_type=event_type,
                organization_id=snapshot.organization_id,
                project_id=snapshot.project_id,
                agent_run_id=snapshot.agent_run_id,
                thread_id=snapshot.thread_id,
                graph_key=snapshot.graph_key,
                graph_version=snapshot.graph_version,
                checkpoint_id=snapshot.checkpoint_id,
                occurred_at=datetime.now(UTC),
                payload={
                    "status": snapshot.status.value,
                    "interrupt_count": len(snapshot.interrupts),
                    "next_nodes": list(snapshot.next_nodes),
                },
                trace_id=trace_id,
            )
        )

    def _assert_same_run(self, snapshot: GraphRunSnapshot, request: GraphRunRequest) -> None:
        self._validate_snapshot(snapshot, request=request)

    def _assert_resume_scope(self, current: GraphRunSnapshot, request: ResumeRequest) -> None:
        if (
            current.organization_id != request.organization_id
            or current.project_id != request.project_id
            or current.agent_run_id != request.agent_run_id
            or current.thread_id != request.thread_id
        ):
            raise GraphRunNotFoundError("AgentRun not found in resume scope")

    def _validate_snapshot(
        self,
        snapshot: GraphRunSnapshot,
        *,
        definition: GraphDefinition | None = None,
        request: GraphRunRequest | None = None,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        task_id: UUID | None = None,
        thread_id: str | None = None,
    ) -> None:
        if request is not None:
            organization_id = request.organization_id
            project_id = request.project_id
            agent_run_id = request.agent_run_id
            task_id = request.task_id
            thread_id = request.thread_id
            definition = self.registry.resolve(
                request.graph_key,
                request.graph_version,
                agent_config_version=request.agent_config_version,
                require_enabled=False,
            )
        assert definition is not None
        if (
            snapshot.organization_id != organization_id
            or snapshot.project_id != project_id
            or snapshot.agent_run_id != agent_run_id
            or snapshot.task_id != task_id
            or snapshot.thread_id != thread_id
            or snapshot.graph_key != definition.graph_key
            or snapshot.graph_version != definition.graph_version
            or snapshot.agent_config_version != definition.agent_config_version
        ):
            raise GraphRunConflictError("executor snapshot identity does not match run binding")
        if snapshot.status == GraphRunStatus.INTERRUPTED and not snapshot.interrupts:
            raise GraphRunConflictError("interrupted snapshot has no resumable interrupt evidence")
        if snapshot.status != GraphRunStatus.INTERRUPTED and snapshot.interrupts:
            raise GraphRunConflictError("non-interrupted snapshot contains active interrupts")


def _find_interrupt(
    interrupts: tuple[GraphInterrupt, ...],
    interrupt_id: str,
) -> GraphInterrupt:
    for interrupt in interrupts:
        if interrupt.interrupt_id == interrupt_id:
            if not interrupt.resumable:
                raise GraphResumeDeniedError("interrupt is not resumable")
            return interrupt
    raise GraphInterruptNotFoundError(f"interrupt not found: {interrupt_id}")


def _start_hash(request: GraphRunRequest, definition: GraphDefinition) -> str:
    payload = {
        "organization_id": str(request.organization_id),
        "project_id": str(request.project_id),
        "agent_run_id": str(request.agent_run_id),
        "task_id": str(request.task_id) if request.task_id else None,
        "thread_id": request.thread_id,
        "graph_key": request.graph_key,
        "graph_version": request.graph_version,
        "agent_config_version": request.agent_config_version,
        "definition_hash": definition.content_hash,
        "input": request.input,
    }
    return _hash_json(payload)


def _resume_hash(request: ResumeRequest, current: GraphRunSnapshot) -> str:
    payload = {
        "organization_id": str(request.organization_id),
        "project_id": str(request.project_id),
        "agent_run_id": str(request.agent_run_id),
        "thread_id": request.thread_id,
        "interrupt_id": request.interrupt_id,
        "decision": request.decision.value,
        "value": request.value,
        "checkpoint_id": current.checkpoint_id,
        "checkpoint_namespace": current.checkpoint_namespace,
    }
    return _hash_json(payload)


def _hash_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
