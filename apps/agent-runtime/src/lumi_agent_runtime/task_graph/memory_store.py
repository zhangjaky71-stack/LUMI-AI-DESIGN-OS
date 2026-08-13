from __future__ import annotations

from dataclasses import replace
from threading import RLock
from uuid import UUID

from .contracts_events import TaskGraphEvent
from .errors import TaskGraphConflictError
from .graph_contracts import TaskGraphSnapshot
from .instantiator import InstantiatedTaskGraph
from .task_contracts import TaskAttempt, TaskSnapshot


class InMemoryTaskGraphStore:
    """Deterministic reference store used for state-machine and restart tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._graphs: dict[UUID, TaskGraphSnapshot] = {}
        self._tasks: dict[UUID, TaskSnapshot] = {}
        self._graph_tasks: dict[UUID, list[UUID]] = {}
        self._attempts: dict[UUID, list[TaskAttempt]] = {}
        self._events: list[TaskGraphEvent] = []

    def install(self, bundle: InstantiatedTaskGraph) -> None:
        with self._lock:
            graph_id = bundle.graph.graph_id
            existing = self._graphs.get(graph_id)
            if existing is not None:
                if existing.provenance.freeze_hash != bundle.graph.provenance.freeze_hash:
                    raise TaskGraphConflictError("TASK_GRAPH_INSTALL_CONFLICT")
                return
            self._graphs[graph_id] = bundle.graph
            self._graph_tasks[graph_id] = []
            for task in bundle.tasks:
                self._tasks[task.task_id] = task
                self._graph_tasks[graph_id].append(task.task_id)
                self._attempts[task.task_id] = []

    def graph(self, graph_id: UUID) -> TaskGraphSnapshot:
        with self._lock:
            return self._graphs[graph_id]

    def task(self, task_id: UUID) -> TaskSnapshot:
        with self._lock:
            return self._tasks[task_id]

    def tasks(self, graph_id: UUID) -> tuple[TaskSnapshot, ...]:
        with self._lock:
            return tuple(self._tasks[item] for item in self._graph_tasks[graph_id])

    def replace_task(
        self,
        task: TaskSnapshot,
        *,
        expected_version: int,
    ) -> TaskSnapshot:
        with self._lock:
            current = self._tasks[task.task_id]
            if current.state_version != expected_version:
                raise TaskGraphConflictError("TASK_STATE_VERSION_CONFLICT")
            if task.state_version != expected_version + 1:
                raise TaskGraphConflictError("TASK_STATE_VERSION_NOT_INCREMENTED")
            self._tasks[task.task_id] = task
            return task

    def replace_graph(
        self,
        graph: TaskGraphSnapshot,
        *,
        expected_version: int,
    ) -> TaskGraphSnapshot:
        with self._lock:
            current = self._graphs[graph.graph_id]
            if current.state_version != expected_version:
                raise TaskGraphConflictError("TASK_GRAPH_STATE_VERSION_CONFLICT")
            if graph.state_version != expected_version + 1:
                raise TaskGraphConflictError("TASK_GRAPH_STATE_VERSION_NOT_INCREMENTED")
            self._graphs[graph.graph_id] = graph
            return graph

    def append_attempt(self, attempt: TaskAttempt) -> None:
        with self._lock:
            rows = self._attempts[attempt.task_id]
            if any(item.attempt_number == attempt.attempt_number for item in rows):
                raise TaskGraphConflictError("TASK_ATTEMPT_DUPLICATE")
            rows.append(attempt)

    def finish_attempt(
        self,
        task_id: UUID,
        attempt_number: int,
        **changes: object,
    ) -> TaskAttempt:
        with self._lock:
            rows = self._attempts[task_id]
            index = next(
                index
                for index, item in enumerate(rows)
                if item.attempt_number == attempt_number
            )
            current = rows[index]
            finished = replace(current, **changes)
            rows[index] = finished
            return finished

    def attempts(self, task_id: UUID) -> tuple[TaskAttempt, ...]:
        with self._lock:
            return tuple(self._attempts[task_id])

    def emit(self, event: TaskGraphEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self) -> tuple[TaskGraphEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def add_dynamic_task(self, task: TaskSnapshot) -> None:
        with self._lock:
            if task.task_id in self._tasks:
                raise TaskGraphConflictError("TASK_DYNAMIC_ID_CONFLICT")
            self._tasks[task.task_id] = task
            self._graph_tasks[task.graph_id].append(task.task_id)
            self._attempts[task.task_id] = []
