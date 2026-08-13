from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol
from uuid import UUID

from .contracts import (
    GraphDefinition,
    GraphInterrupt,
    GraphRunRequest,
    GraphRunSnapshot,
    GraphRunStatus,
    InterruptKind,
    ResumeRequest,
)
from .errors import (
    GraphCheckpointRequiredError,
    GraphExecutionError,
    GraphNotFoundError,
    GraphRunConflictError,
)


@dataclass(frozen=True, slots=True)
class ThreadGraphBinding:
    thread_id: str
    graph_key: str
    graph_version: str
    agent_config_version: str
    task_id: UUID | None = None


class ThreadGraphBindingResolver(Protocol):
    async def resolve_thread(self, thread_id: str) -> ThreadGraphBinding: ...


class DurableCompiledGraphRegistry:
    def __init__(self) -> None:
        self._graphs: dict[tuple[str, str], tuple[GraphDefinition, Any]] = {}

    def register(self, definition: GraphDefinition, graph: Any) -> None:
        key = (definition.graph_key, definition.graph_version)
        existing = self._graphs.get(key)
        if existing is not None and existing[0].content_hash != definition.content_hash:
            raise GraphRunConflictError(
                f"compiled graph version changed content: {definition.identity}"
            )
        if getattr(graph, "checkpointer", None) is None:
            raise GraphCheckpointRequiredError(
                f"compiled graph has no checkpointer: {definition.identity}"
            )
        self._graphs[key] = (definition, graph)

    def resolve(
        self,
        graph_key: str,
        graph_version: str,
        *,
        agent_config_version: str,
    ) -> tuple[GraphDefinition, Any]:
        try:
            definition, graph = self._graphs[(graph_key, graph_version)]
        except KeyError as exc:
            raise GraphNotFoundError(
                f"compiled graph unavailable: {graph_key}@{graph_version}"
            ) from exc
        if definition.agent_config_version != agent_config_version:
            raise GraphRunConflictError("agent config version mismatch")
        return definition, graph


class DurableLangGraphExecutor:
    """Current LangGraph runtime adapter with durable LUMI thread/version binding."""

    def __init__(
        self,
        *,
        graphs: DurableCompiledGraphRegistry,
        bindings: ThreadGraphBindingResolver,
    ) -> None:
        self.graphs = graphs
        self.bindings = bindings

    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot:
        definition, graph = self.graphs.resolve(
            request.graph_key,
            request.graph_version,
            agent_config_version=request.agent_config_version,
        )
        try:
            await graph.ainvoke(
                dict(request.input),
                config=_thread_config(request.thread_id, trace_id=request.trace_id),
            )
        except Exception as exc:
            raise GraphExecutionError("LangGraph start failed") from exc
        return await self._snapshot(
            definition=definition,
            graph=graph,
            organization_id=request.organization_id,
            project_id=request.project_id,
            agent_run_id=request.agent_run_id,
            task_id=request.task_id,
            thread_id=request.thread_id,
        )

    async def resume(
        self,
        request: ResumeRequest,
        *,
        normalized_value: Any,
    ) -> GraphRunSnapshot:
        binding = await self.bindings.resolve_thread(request.thread_id)
        if binding.thread_id != request.thread_id:
            raise GraphRunConflictError("thread binding identity mismatch")
        definition, graph = self.graphs.resolve(
            binding.graph_key,
            binding.graph_version,
            agent_config_version=binding.agent_config_version,
        )
        command_type = getattr(import_module("langgraph.types"), "Command")
        try:
            await graph.ainvoke(
                command_type(resume=normalized_value),
                config=_thread_config(request.thread_id, trace_id=request.trace_id),
            )
        except Exception as exc:
            raise GraphExecutionError("LangGraph resume failed") from exc
        return await self._snapshot(
            definition=definition,
            graph=graph,
            organization_id=request.organization_id,
            project_id=request.project_id,
            agent_run_id=request.agent_run_id,
            task_id=binding.task_id,
            thread_id=request.thread_id,
        )

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
        resolved, graph = self.graphs.resolve(
            definition.graph_key,
            definition.graph_version,
            agent_config_version=definition.agent_config_version,
        )
        return await self._snapshot(
            definition=resolved,
            graph=graph,
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            thread_id=thread_id,
        )

    async def cancel(
        self,
        *,
        definition: GraphDefinition,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        thread_id: str,
    ) -> GraphRunSnapshot:
        binding = await self.bindings.resolve_thread(thread_id)
        current = await self.snapshot(
            definition=definition,
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            task_id=binding.task_id,
            thread_id=thread_id,
        )
        # Do not rewrite checkpoint history. LUMI terminalizes the run-control record and
        # separately signals cancellation to active Tool/Model/Sandbox operations.
        return replace(
            current,
            status=GraphRunStatus.CANCELLED,
            next_nodes=(),
            interrupts=(),
            updated_at=datetime.now(UTC),
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
    ) -> GraphRunSnapshot:
        try:
            raw = await graph.aget_state(_thread_config(thread_id, trace_id=None))
        except Exception as exc:
            raise GraphExecutionError("LangGraph checkpoint read failed") from exc
        if raw is None:
            raise GraphExecutionError("LangGraph checkpoint state missing")
        values = getattr(raw, "values", {})
        if not isinstance(values, dict):
            raise GraphExecutionError("LangGraph state values must be an object")
        raw_next = getattr(raw, "next", ()) or ()
        next_nodes = tuple(str(item) for item in raw_next)
        interrupts = _interrupts(raw)
        status = (
            GraphRunStatus.INTERRUPTED
            if interrupts
            else GraphRunStatus.SUCCEEDED
            if not next_nodes
            else GraphRunStatus.RUNNING
        )
        raw_config = getattr(raw, "config", {}) or {}
        configurable = raw_config.get("configurable", {}) if isinstance(raw_config, dict) else {}
        if not isinstance(configurable, dict):
            configurable = {}
        checkpoint_id = configurable.get("checkpoint_id")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        created_at = _datetime(getattr(raw, "created_at", None))
        return GraphRunSnapshot(
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            thread_id=thread_id,
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            status=status,
            checkpoint_id=str(checkpoint_id) if checkpoint_id else None,
            checkpoint_namespace=str(checkpoint_ns or ""),
            state_values=dict(values),
            next_nodes=next_nodes,
            interrupts=interrupts,
            created_at=created_at,
            updated_at=datetime.now(UTC),
        )


def _thread_config(thread_id: str, *, trace_id: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"lumi_thread_id": thread_id}
    if trace_id:
        metadata["lumi_trace_id"] = trace_id
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": metadata,
    }


def _interrupts(raw: Any) -> tuple[GraphInterrupt, ...]:
    result: list[GraphInterrupt] = []
    for task in getattr(raw, "tasks", ()) or ():
        node_name = getattr(task, "name", None)
        for item in getattr(task, "interrupts", ()) or ():
            raw_id = getattr(item, "id", None)
            if not raw_id:
                raise GraphExecutionError("LangGraph interrupt has no stable id")
            value = getattr(item, "value", None)
            payload = dict(value) if isinstance(value, dict) else {"value": value}
            result.append(
                GraphInterrupt(
                    interrupt_id=str(raw_id),
                    kind=_kind(payload),
                    namespace=tuple(str(part) for part in (getattr(item, "ns", ()) or ())),
                    node_name=str(node_name) if node_name else None,
                    payload=payload,
                    resumable=bool(getattr(item, "resumable", True)),
                )
            )
    return tuple(result)


def _kind(payload: dict[str, Any]) -> InterruptKind:
    raw = payload.get("kind")
    try:
        return InterruptKind(str(raw))
    except ValueError:
        return InterruptKind.REVIEW


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)
