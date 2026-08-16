from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langgraph.types import Command

from .contracts import (
    GraphDefinition,
    ResumeRunCommand,
    RunControlSnapshot,
    RunStatus,
    SafeRunEvent,
    StartRunCommand,
    validate_run_state,
)
from .errors import (
    GraphExecutionFailed,
    GraphNotFound,
    GraphVersionMismatch,
    ResumeDenied,
    ResumeVersionConflict,
    RunConflict,
    RunNotFound,
)
from .ports import CancellationPort, EventSink, OperationGuard, ResumeAuthorizer, RunControlStore

_TERMINAL = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


class CompiledGraphRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[GraphDefinition, Any]] = {}

    def register(self, definition: GraphDefinition, graph: Any) -> None:
        if getattr(graph, "checkpointer", None) is None:
            raise RunConflict("GRAPH_CHECKPOINTER_REQUIRED")
        key = (definition.graph_key, definition.graph_version)
        existing = self._entries.get(key)
        if existing is not None and existing[0].content_hash != definition.content_hash:
            raise RunConflict("GRAPH_VERSION_CONTENT_CHANGED")
        self._entries[key] = (definition, graph)

    def resolve(self, graph_key: str, graph_version: str) -> tuple[GraphDefinition, Any]:
        try:
            return self._entries[(graph_key, graph_version)]
        except KeyError as exc:
            raise GraphNotFound(f"{graph_key}@{graph_version}") from exc


class LangGraphRuntime:
    def __init__(self, registry: CompiledGraphRegistry) -> None:
        self.registry = registry

    async def start(self, command: StartRunCommand) -> RunControlSnapshot:
        definition, graph = self.registry.resolve(command.graph_key, command.graph_version)
        self._assert_definition(command, definition)
        config = _config(command.effective_thread_id, command.trace_id)
        try:
            await graph.ainvoke(command.initial_state(), config=config)
        except Exception as exc:
            raise GraphExecutionFailed("LANGGRAPH_START_FAILED") from exc
        return await self._snapshot(
            definition=definition,
            graph=graph,
            organization_id=command.organization_id,
            project_id=command.project_id,
            agent_run_id=command.agent_run_id,
            task_id=command.task_id,
            thread_id=command.effective_thread_id,
            resume_version=1,
        )

    async def resume(
        self,
        command: ResumeRunCommand,
        *,
        normalized_value: Any,
        task_id: UUID | None,
    ) -> RunControlSnapshot:
        definition, graph = self.registry.resolve(
            command.expected_graph_key, command.expected_graph_version
        )
        if definition.code_git_sha != command.expected_code_git_sha:
            raise GraphVersionMismatch("GRAPH_CODE_SHA_MISMATCH")
        try:
            await graph.ainvoke(
                Command(resume=normalized_value),
                config=_config(command.thread_id, command.trace_id),
            )
        except Exception as exc:
            raise GraphExecutionFailed("LANGGRAPH_RESUME_FAILED") from exc
        return await self._snapshot(
            definition=definition,
            graph=graph,
            organization_id=command.organization_id,
            project_id=command.project_id,
            agent_run_id=command.agent_run_id,
            task_id=task_id,
            thread_id=command.thread_id,
            resume_version=command.resume_version + 1,
        )

    async def _snapshot(
        self,
        *,
        definition: GraphDefinition,
        graph: Any,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        task_id: UUID | None,
        thread_id: str,
        resume_version: int,
    ) -> RunControlSnapshot:
        try:
            raw = await graph.aget_state(_config(thread_id, None))
        except Exception as exc:
            raise GraphExecutionFailed("LANGGRAPH_CHECKPOINT_READ_FAILED") from exc
        if raw is None:
            raise GraphExecutionFailed("LANGGRAPH_CHECKPOINT_MISSING")
        values = getattr(raw, "values", {}) or {}
        if not isinstance(values, dict):
            raise GraphExecutionFailed("LANGGRAPH_STATE_NOT_OBJECT")
        validate_run_state(values)
        interrupts = _interrupts(raw)
        next_nodes = tuple(str(item) for item in (getattr(raw, "next", ()) or ()))
        status = _status(values, interrupts, next_nodes)
        raw_config = getattr(raw, "config", {}) or {}
        configurable = raw_config.get("configurable", {}) if isinstance(raw_config, dict) else {}
        checkpoint_id = configurable.get("checkpoint_id") if isinstance(configurable, dict) else None
        checkpoint_ns = configurable.get("checkpoint_ns", "") if isinstance(configurable, dict) else ""
        now = datetime.now(UTC)
        return RunControlSnapshot(
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            thread_id=thread_id,
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            code_git_sha=definition.code_git_sha,
            status=status,
            checkpoint_id=str(checkpoint_id) if checkpoint_id else None,
            checkpoint_namespace=str(checkpoint_ns or ""),
            state=values,
            next_nodes=next_nodes,
            interrupts=interrupts,
            resume_version=resume_version,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _assert_definition(command: StartRunCommand, definition: GraphDefinition) -> None:
        if (
            command.agent_config_version != definition.agent_config_version
            or command.code_git_sha != definition.code_git_sha
        ):
            raise GraphVersionMismatch("GRAPH_DEFINITION_BINDING_MISMATCH")


class LangGraphControlPlane:
    def __init__(
        self,
        *,
        runtime: LangGraphRuntime,
        store: RunControlStore,
        operation_guard: OperationGuard,
        resume_authorizer: ResumeAuthorizer,
        cancellation: CancellationPort,
        events: EventSink,
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.operation_guard = operation_guard
        self.resume_authorizer = resume_authorizer
        self.cancellation = cancellation
        self.events = events

    async def start(self, command: StartRunCommand) -> RunControlSnapshot:
        request_hash = _hash(
            {
                "organization_id": str(command.organization_id),
                "project_id": str(command.project_id),
                "agent_run_id": str(command.agent_run_id),
                "thread_id": command.effective_thread_id,
                "graph_key": command.graph_key,
                "graph_version": command.graph_version,
                "code_git_sha": command.code_git_sha,
                "brief_version": command.brief_version,
            }
        )

        async def invoke() -> RunControlSnapshot:
            existing = await self.store.load(
                organization_id=command.organization_id,
                agent_run_id=command.agent_run_id,
            )
            if existing is not None:
                self._assert_start_identity(existing, command)
                return existing
            snapshot = await self.runtime.start(command)
            await self.store.create(snapshot)
            await self._emit_snapshot(snapshot, initial=True)
            return snapshot

        return await self.operation_guard.execute(
            organization_id=command.organization_id,
            operation_id=command.operation_id,
            operation_type="langgraph.start",
            request_hash=request_hash,
            invoke=invoke,
        )

    async def resume(self, command: ResumeRunCommand) -> RunControlSnapshot:
        current = await self.store.load(
            organization_id=command.organization_id,
            agent_run_id=command.agent_run_id,
        )
        if current is None:
            raise RunNotFound(str(command.agent_run_id))
        self._assert_resume_identity(current, command)
        request_hash = _hash(
            {
                "agent_run_id": str(command.agent_run_id),
                "thread_id": command.thread_id,
                "interrupt_id": command.interrupt_id,
                "resume_version": command.resume_version,
                "kind": command.kind.value,
                "value": command.value,
            }
        )

        async def invoke() -> RunControlSnapshot:
            fresh = await self.store.load(
                organization_id=command.organization_id,
                agent_run_id=command.agent_run_id,
            )
            if fresh is None:
                raise RunNotFound(str(command.agent_run_id))
            self._assert_resume_identity(fresh, command)
            if fresh.status in _TERMINAL:
                return fresh
            if command.resume_version != fresh.resume_version:
                raise ResumeVersionConflict("STALE_RESUME_VERSION")
            interrupt = _find_interrupt(fresh, command.interrupt_id)
            normalized = await self.resume_authorizer.authorize(
                organization_id=command.organization_id,
                project_id=command.project_id,
                agent_run_id=command.agent_run_id,
                interrupt_id=command.interrupt_id,
                resume_version=command.resume_version,
                value=command.value,
            )
            if interrupt.get("kind") not in {command.kind.value, "review"}:
                raise ResumeDenied("RESUME_KIND_MISMATCH")
            resumed = await self.runtime.resume(
                command,
                normalized_value=normalized,
                task_id=fresh.task_id,
            )
            await self.store.compare_and_set(
                resumed,
                expected_checkpoint_id=fresh.checkpoint_id,
                expected_resume_version=fresh.resume_version,
            )
            await self._emit_snapshot(resumed, initial=False)
            return resumed

        return await self.operation_guard.execute(
            organization_id=command.organization_id,
            operation_id=command.operation_id,
            operation_type="langgraph.resume",
            request_hash=request_hash,
            invoke=invoke,
        )

    async def cancel(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
    ) -> RunControlSnapshot:
        current = await self.store.load(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
        )
        if current is None or current.project_id != project_id:
            raise RunNotFound(str(agent_run_id))
        request_hash = _hash({"agent_run_id": str(agent_run_id), "action": "cancel"})

        async def invoke() -> RunControlSnapshot:
            fresh = await self.store.load(
                organization_id=organization_id,
                agent_run_id=agent_run_id,
            )
            if fresh is None:
                raise RunNotFound(str(agent_run_id))
            if fresh.status in _TERMINAL:
                return fresh
            await self.cancellation.cancel_pending(fresh.state)
            await self.cancellation.release_reservations(fresh.state)
            cancelled = replace(
                fresh,
                status=RunStatus.CANCELLED,
                state={**fresh.state, "status": RunStatus.CANCELLED.value},
                next_nodes=(),
                interrupts=(),
                updated_at=datetime.now(UTC),
            )
            await self.store.compare_and_set(
                cancelled,
                expected_checkpoint_id=fresh.checkpoint_id,
                expected_resume_version=fresh.resume_version,
            )
            await self.events.publish(
                SafeRunEvent(
                    "run.cancelled",
                    organization_id,
                    project_id,
                    agent_run_id,
                    payload={"status": RunStatus.CANCELLED.value},
                )
            )
            return cancelled

        return await self.operation_guard.execute(
            organization_id=organization_id,
            operation_id=operation_id,
            operation_type="langgraph.cancel",
            request_hash=request_hash,
            invoke=invoke,
        )

    async def _emit_snapshot(self, snapshot: RunControlSnapshot, *, initial: bool) -> None:
        if initial:
            await self.events.publish(
                SafeRunEvent(
                    "run.started",
                    snapshot.organization_id,
                    snapshot.project_id,
                    snapshot.agent_run_id,
                    payload={
                        "graph_key": snapshot.graph_key,
                        "graph_version": snapshot.graph_version,
                    },
                )
            )
        for item in snapshot.interrupts:
            event_type = (
                "run.waiting_external"
                if item.get("kind") == "external_job"
                else "approval.required"
            )
            await self.events.publish(
                SafeRunEvent(
                    event_type,
                    snapshot.organization_id,
                    snapshot.project_id,
                    snapshot.agent_run_id,
                    payload={
                        "interrupt_id": item.get("id"),
                        "kind": item.get("kind"),
                        "node": item.get("node"),
                    },
                )
            )
        if snapshot.status is RunStatus.SUCCEEDED:
            await self.events.publish(
                SafeRunEvent(
                    "run.completed",
                    snapshot.organization_id,
                    snapshot.project_id,
                    snapshot.agent_run_id,
                    payload={"status": RunStatus.SUCCEEDED.value},
                )
            )

    @staticmethod
    def _assert_start_identity(snapshot: RunControlSnapshot, command: StartRunCommand) -> None:
        if (
            snapshot.organization_id != command.organization_id
            or snapshot.project_id != command.project_id
            or snapshot.thread_id != command.effective_thread_id
            or snapshot.graph_key != command.graph_key
            or snapshot.graph_version != command.graph_version
            or snapshot.code_git_sha != command.code_git_sha
        ):
            raise RunConflict("START_REPLAY_BINDING_MISMATCH")

    @staticmethod
    def _assert_resume_identity(snapshot: RunControlSnapshot, command: ResumeRunCommand) -> None:
        if (
            snapshot.organization_id != command.organization_id
            or snapshot.project_id != command.project_id
            or snapshot.thread_id != command.thread_id
        ):
            raise RunNotFound(str(command.agent_run_id))
        if (
            snapshot.graph_key != command.expected_graph_key
            or snapshot.graph_version != command.expected_graph_version
            or snapshot.code_git_sha != command.expected_code_git_sha
        ):
            raise GraphVersionMismatch("RESUME_GRAPH_VERSION_MISMATCH")


def _interrupts(raw: Any) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for task in getattr(raw, "tasks", ()) or ():
        node = getattr(task, "name", None)
        for item in getattr(task, "interrupts", ()) or ():
            interrupt_id = getattr(item, "id", None)
            if not interrupt_id:
                raise GraphExecutionFailed("LANGGRAPH_INTERRUPT_ID_MISSING")
            value = getattr(item, "value", None)
            payload = value if isinstance(value, dict) else {"value": value}
            result.append(
                {
                    "id": str(interrupt_id),
                    "kind": str(payload.get("kind", "review")),
                    "node": str(node) if node else None,
                    "payload": payload,
                    "resumable": bool(getattr(item, "resumable", True)),
                }
            )
    return tuple(result)


def _status(
    values: dict[str, Any],
    interrupts: tuple[dict[str, Any], ...],
    next_nodes: tuple[str, ...],
) -> RunStatus:
    if interrupts:
        if any(item.get("kind") == "external_job" for item in interrupts):
            return RunStatus.WAITING_EXTERNAL
        return RunStatus.WAITING_USER
    explicit = values.get("status")
    try:
        status = RunStatus(str(explicit))
    except ValueError:
        status = RunStatus.RUNNING if next_nodes else RunStatus.SUCCEEDED
    if not next_nodes and status is RunStatus.RUNNING:
        return RunStatus.SUCCEEDED
    return status


def _find_interrupt(snapshot: RunControlSnapshot, interrupt_id: str) -> dict[str, Any]:
    for item in snapshot.interrupts:
        if item.get("id") == interrupt_id:
            if not item.get("resumable", True):
                raise ResumeDenied("INTERRUPT_NOT_RESUMABLE")
            return item
    raise ResumeDenied("INTERRUPT_NOT_FOUND")


def _config(thread_id: str, trace_id: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"lumi_thread_id": thread_id}
    if trace_id:
        metadata["lumi_trace_id"] = trace_id
    return {"configurable": {"thread_id": thread_id}, "metadata": metadata}


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
