from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from typing import Any
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


class CompiledLangGraphRegistry:
    """Exact-version registry of already compiled LangGraph graphs.

    A graph is accepted only when it has a checkpointer. NODE-28 never silently compiles a
    durable production graph without persistence and never resolves an unspecified latest
    version at run time.
    """

    def __init__(self) -> None:
        self._graphs: dict[tuple[str, str], Any] = {}

    def register(self, definition: GraphDefinition, graph: Any) -> None:
        key = (definition.graph_key, definition.graph_version)
        existing = self._graphs.get(key)
        if existing is not None and existing is not graph:
            raise GraphRunConflictError(
                f"compiled graph version already registered: {definition.identity}"
            )
        if getattr(graph, "checkpointer", None) is None:
            raise GraphCheckpointRequiredError(
                f"compiled graph has no checkpointer: {definition.identity}"
            )
        self._graphs[key] = graph

    def resolve(self, definition: GraphDefinition) -> Any:
        try:
            return self._graphs[(definition.graph_key, definition.graph_version)]
        except KeyError as exc:
            raise GraphNotFoundError(
                f"compiled graph unavailable: {definition.identity}"
            ) from exc


class LangGraphExecutor:
    """Adapter for the current LangGraph durable-execution model.

    The adapter uses one stable `thread_id` for the AgentRun. Resume uses LangGraph
    ``Command(resume=...)`` against that persisted thread rather than re-invoking the graph
    from original input. Raw LangGraph objects never escape this adapter.
    """

    def __init__(
        self,
        *,
        definitions: dict[tuple[str, str], GraphDefinition],
        graphs: CompiledLangGraphRegistry,
    ) -> None:
        self.definitions = dict(definitions)
        self.graphs = graphs

    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot:
        definition = self._definition(
            request.graph_key,
            request.graph_version,
            request.agent_config_version,
        )
        graph = self.graphs.resolve(definition)
        config = _thread_config(request.thread_id, trace_id=request.trace_id)
        try:
            await graph.ainvoke(dict(request.input), config=config)
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
        # Resolve graph identity from the current thread's state. LUMI never asks the
        # caller to choose a new graph version while resuming an existing AgentRun.
        definition, graph = await self._definition_for_thread(request.thread_id)
        command_type = getattr(import_module("langgraph.types"), "Command")
        config = _thread_config(request.thread_id, trace_id=request.trace_id)
        try:
            await graph.ainvoke(command_type(resume=normalized_value), config=config)
        except Exception as exc:
            raise GraphExecutionError("LangGraph resume failed") from exc
        return await self._snapshot(
            definition=definition,
            graph=graph,
            organization_id=request.organization_id,
            project_id=request.project_id,
            agent_run_id=request.agent_run_id,
            task_id=None,
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
        graph = self.graphs.resolve(definition)
        return await self._snapshot(
            definition=definition,
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
        # LangGraph checkpoints are immutable history; cancellation is a LUMI run-control
        # terminal state, not a rewrite of checkpoint history. In-flight provider/tool work
        # must use its own NODE-20/21/22/25 cooperative cancellation path.
        current = await self.snapshot(
            definition=definition,
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            task_id=None,
            thread_id=thread_id,
        )
        return replace(
            current,
            status=GraphRunStatus.CANCELLED,
            interrupts=(),
            next_nodes=(),
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
            raise GraphExecutionError("LangGraph returned no checkpoint state")
        values = getattr(raw, "values", {})
        if not isinstance(values, dict):
            raise GraphExecutionError("LangGraph state values must be an object")
        next_nodes_raw = getattr(raw, "next", ()) or ()
        next_nodes = tuple(str(item) for item in next_nodes_raw)
        interrupts = _interrupts_from_state(raw)
        if interrupts:
            status = GraphRunStatus.INTERRUPTED
        elif not next_nodes:
            status = GraphRunStatus.SUCCEEDED
        else:
            status = GraphRunStatus.RUNNING
        config = getattr(raw, "config", {}) or {}
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        if not isinstance(configurable, dict):
            configurable = {}
        checkpoint_id = configurable.get("checkpoint_id")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        created = _coerce_datetime(getattr(raw, "created_at", None))
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
            created_at=created,
            updated_at=datetime.now(UTC),
        )

    def _definition(
        self,
        graph_key: str,
        graph_version: str,
        agent_config_version: str,
    ) -> GraphDefinition:
        try:
            definition = self.definitions[(graph_key, graph_version)]
        except KeyError as exc:
            raise GraphNotFoundError(f"graph not registered: {graph_key}@{graph_version}") from exc
        if definition.agent_config_version != agent_config_version:
            raise GraphRunConflictError("agent config version mismatch")
        return definition

    async def _definition_for_thread(self, thread_id: str) -> tuple[GraphDefinition, Any]:
        # A thread is already immutably bound by LUMI GraphRunStore. The executor registry
        # does not infer a graph from arbitrary state content. There must be exactly one
        # registered compiled graph whose current checkpoint contains this thread.
        matches: list[tuple[GraphDefinition, Any]] = []
        for key, definition in self.definitions.items():
            graph = self.graphs.resolve(definition)
            try:
                state = await graph.aget_state(_thread_config(thread_id, trace_id=None))
            except Exception:
                continue
            config = getattr(state, "config", None) if state is not None else None
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            if isinstance(configurable, dict) and configurable.get("thread_id") == thread_id:
                matches.append((definition, graph))
        if len(matches) != 1:
            raise GraphRunConflictError(
                "thread must resolve to exactly one immutable compiled graph"
            )
        return matches[0]


def _thread_config(thread_id: str, *, trace_id: str | None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
        "metadata": {"lumi_thread_id": thread_id},
    }
    if trace_id:
        config["metadata"]["lumi_trace_id"] = trace_id
    return config


def _interrupts_from_state(raw: Any) -> tuple[GraphInterrupt, ...]:
    found: list[GraphInterrupt] = []
    tasks = getattr(raw, "tasks", ()) or ()
    for task in tasks:
        task_name = getattr(task, "name", None)
        raw_interrupts = getattr(task, "interrupts", ()) or ()
        for item in raw_interrupts:
            value = getattr(item, "value", None)
            payload = value if isinstance(value, dict) else {"value": value}
            kind = _interrupt_kind(payload)
            raw_id = getattr(item, "id", None)
            if raw_id is None:
                raise GraphExecutionError("LangGraph interrupt is missing stable id")
            namespace_raw = getattr(item, "ns", ()) or ()
            namespace = tuple(str(part) for part in namespace_raw)
            resumable = bool(getattr(item, "resumable", True))
            found.append(
                GraphInterrupt(
                    interrupt_id=str(raw_id),
                    kind=kind,
                    namespace=namespace,
                    node_name=str(task_name) if task_name is not None else None,
                    payload=dict(payload),
                    resumable=resumable,
                )
            )
    return tuple(found)


def _interrupt_kind(payload: dict[str, Any]) -> InterruptKind:
    raw = payload.get("kind")
    try:
        return InterruptKind(str(raw))
    except ValueError:
        return InterruptKind.REVIEW


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)
