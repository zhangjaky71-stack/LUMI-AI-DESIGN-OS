from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from .contracts import TaskGraphDefinition, TaskGraphState, TaskKind, TaskState
from .errors import TaskGraphDefinitionError, TaskGraphStateError
from .scheduler import TaskGraphScheduler
from .store import TaskGraphStore


class TaskGraphDefinitionResolver(Protocol):
    async def resolve(self, state: dict[str, Any]) -> TaskGraphDefinition: ...


class TaskGraphClock(Protocol):
    def now(self) -> datetime: ...


class UtcTaskGraphClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ControlPlaneTaskGraphAdapter:
    """Structural adapter for NODE-28 `TaskGraphPort`.

    The existing port is intentionally tiny (`ensure_task_graph`, `next_route`).
    Worker claiming and completion remain explicit scheduler operations so route
    inspection never performs a hidden side effect.
    """

    def __init__(
        self,
        *,
        scheduler: TaskGraphScheduler,
        store: TaskGraphStore,
        definitions: TaskGraphDefinitionResolver,
        clock: TaskGraphClock | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.store = store
        self.definitions = definitions
        self.clock = clock or UtcTaskGraphClock()

    async def ensure_task_graph(self, state: dict[str, Any]) -> list[str]:
        definition = await self.definitions.resolve(state)
        _assert_state_identity(state, definition)
        graph = await self.scheduler.ensure_graph(definition, now=self.clock.now())
        await self.scheduler.refresh_ready(graph.graph_id, now=self.clock.now())
        tasks = await self.scheduler.tasks(graph.graph_id)
        return [
            str(task.task_id)
            for task in _ordered(tasks)
            if task.status in {TaskState.READY, TaskState.RUNNING}
        ]

    async def next_route(self, state: dict[str, Any]) -> str:
        organization_id, agent_run_id = _run_identity(state)
        graph = await self.store.find_graph_by_run(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
        )
        if graph is None:
            raise TaskGraphStateError("TASK_GRAPH_NOT_INSTANTIATED")
        if graph.project_id != UUID(str(state.get("project_id"))):
            raise TaskGraphStateError("TASK_GRAPH_PROJECT_MISMATCH")
        await self.scheduler.refresh_ready(graph.graph_id, now=self.clock.now())
        graph = await self.scheduler.graph(graph.graph_id)
        tasks = await self.scheduler.tasks(graph.graph_id)

        if graph.status in {
            TaskGraphState.SUCCEEDED,
            TaskGraphState.FAILED_FINAL,
            TaskGraphState.CANCELLED,
        }:
            return "done"
        if graph.status is TaskGraphState.PAUSED:
            raise TaskGraphStateError("TASK_GRAPH_PAUSED")
        if graph.status in {
            TaskGraphState.CANCEL_REQUESTED,
            TaskGraphState.FAILURE_DRAINING,
        }:
            has_running = any(task.status is TaskState.RUNNING for task in tasks)
            return _route_running(tasks) if has_running else "done"

        ready = [task for task in _ordered(tasks) if task.status is TaskState.READY]
        if ready:
            return _kind_route(ready[0].kind)
        waiting_user = [task for task in _ordered(tasks) if task.status is TaskState.WAITING_USER]
        if waiting_user:
            return "approval"
        waiting_external = [
            task for task in _ordered(tasks) if task.status is TaskState.WAITING_EXTERNAL
        ]
        if waiting_external:
            return "wait_external"
        running = [task for task in _ordered(tasks) if task.status is TaskState.RUNNING]
        if running:
            return _kind_route(running[0].kind)
        return "done"


def _ordered(tasks: tuple[Any, ...]) -> list[Any]:
    return sorted(tasks, key=lambda item: (-item.priority, item.task_key))


def _kind_route(kind: TaskKind) -> str:
    return {
        TaskKind.DETERMINISTIC: "deterministic",
        TaskKind.AGENTIC: "agentic",
        TaskKind.SIDE_EFFECT: "side_effect",
        TaskKind.WAIT_EXTERNAL: "wait_external",
        TaskKind.APPROVAL: "approval",
    }[kind]


def _route_running(tasks: tuple[Any, ...]) -> str:
    running = [task for task in _ordered(tasks) if task.status is TaskState.RUNNING]
    return "done" if not running else _kind_route(running[0].kind)


def _run_identity(state: dict[str, Any]) -> tuple[UUID, UUID]:
    try:
        return UUID(str(state["organization_id"])), UUID(str(state["run_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise TaskGraphStateError("TASK_GRAPH_CONTROL_STATE_IDENTITY_INVALID") from exc


def _assert_state_identity(state: dict[str, Any], definition: TaskGraphDefinition) -> None:
    organization_id, agent_run_id = _run_identity(state)
    try:
        project_id = UUID(str(state["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise TaskGraphStateError("TASK_GRAPH_CONTROL_STATE_PROJECT_INVALID") from exc
    if organization_id != definition.organization_id:
        raise TaskGraphDefinitionError("TASK_GRAPH_ORGANIZATION_MISMATCH")
    if project_id != definition.project_id:
        raise TaskGraphDefinitionError("TASK_GRAPH_PROJECT_MISMATCH")
    if agent_run_id != definition.agent_run_id:
        raise TaskGraphDefinitionError("TASK_GRAPH_RUN_MISMATCH")
