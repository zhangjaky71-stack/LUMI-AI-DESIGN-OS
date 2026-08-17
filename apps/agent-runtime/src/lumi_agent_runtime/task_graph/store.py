from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import UUID

from .contracts import (
    TaskAttempt,
    TaskGraphDefinition,
    TaskGraphEvent,
    TaskGraphSnapshot,
    TaskSnapshot,
)
from .errors import TaskGraphConflictError


class TaskGraphTransaction(Protocol):
    def definition(self) -> TaskGraphDefinition: ...

    def graph(self) -> TaskGraphSnapshot: ...

    def tasks(self) -> tuple[TaskSnapshot, ...]: ...

    def task(self, task_id: UUID) -> TaskSnapshot: ...

    def put_graph(self, snapshot: TaskGraphSnapshot, *, expected_version: int) -> None: ...

    def put_task(self, snapshot: TaskSnapshot, *, expected_version: int) -> None: ...

    def attempt(self, task_id: UUID, attempt_number: int) -> TaskAttempt: ...

    def append_attempt(self, attempt: TaskAttempt) -> None: ...

    def replace_attempt(self, attempt: TaskAttempt) -> None: ...

    def append_event(self, event: TaskGraphEvent) -> None: ...


class TaskGraphStore(Protocol):
    async def create_graph(
        self,
        definition: TaskGraphDefinition,
        graph: TaskGraphSnapshot,
        tasks: tuple[TaskSnapshot, ...],
    ) -> TaskGraphSnapshot: ...

    async def find_graph_by_run(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
    ) -> TaskGraphSnapshot | None: ...

    def transaction(self, graph_id: UUID): ...


class _MemoryTransaction:
    def __init__(self, store: InMemoryTaskGraphStore, graph_id: UUID) -> None:
        self._store = store
        self._graph_id = graph_id

    def definition(self) -> TaskGraphDefinition:
        return self._store._definitions[self._graph_id]

    def graph(self) -> TaskGraphSnapshot:
        return self._store._graphs[self._graph_id]

    def tasks(self) -> tuple[TaskSnapshot, ...]:
        values = self._store._tasks[self._graph_id].values()
        return tuple(sorted(values, key=lambda item: item.task_key))

    def task(self, task_id: UUID) -> TaskSnapshot:
        return self._store._tasks[self._graph_id][task_id]

    def put_graph(self, snapshot: TaskGraphSnapshot, *, expected_version: int) -> None:
        current = self.graph()
        if current.state_version != expected_version:
            raise TaskGraphConflictError("TASK_GRAPH_CAS_CONFLICT")
        if snapshot.graph_id != self._graph_id:
            raise TaskGraphConflictError("TASK_GRAPH_ID_MISMATCH")
        self._store._graphs[self._graph_id] = snapshot

    def put_task(self, snapshot: TaskSnapshot, *, expected_version: int) -> None:
        current = self.task(snapshot.task_id)
        if current.state_version != expected_version:
            raise TaskGraphConflictError("TASK_CAS_CONFLICT")
        if snapshot.graph_id != self._graph_id:
            raise TaskGraphConflictError("TASK_GRAPH_ID_MISMATCH")
        self._store._tasks[self._graph_id][snapshot.task_id] = snapshot

    def attempt(self, task_id: UUID, attempt_number: int) -> TaskAttempt:
        return self._store._attempts[(task_id, attempt_number)]

    def append_attempt(self, attempt: TaskAttempt) -> None:
        key = (attempt.task_id, attempt.attempt_number)
        if key in self._store._attempts:
            raise TaskGraphConflictError("TASK_ATTEMPT_DUPLICATE")
        self._store._attempts[key] = attempt

    def replace_attempt(self, attempt: TaskAttempt) -> None:
        key = (attempt.task_id, attempt.attempt_number)
        if key not in self._store._attempts:
            raise TaskGraphConflictError("TASK_ATTEMPT_MISSING")
        self._store._attempts[key] = attempt

    def append_event(self, event: TaskGraphEvent) -> None:
        self._store._events.setdefault(self._graph_id, []).append(event)


class InMemoryTaskGraphStore:
    """Deterministic transaction reference store for NODE-33 tests and local execution.

    Production stores must preserve the same transaction/CAS semantics with durable row locking.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._definitions: dict[UUID, TaskGraphDefinition] = {}
        self._graphs: dict[UUID, TaskGraphSnapshot] = {}
        self._tasks: dict[UUID, dict[UUID, TaskSnapshot]] = {}
        self._attempts: dict[tuple[UUID, int], TaskAttempt] = {}
        self._events: dict[UUID, list[TaskGraphEvent]] = {}
        self._run_index: dict[tuple[UUID, UUID], UUID] = {}

    async def create_graph(
        self,
        definition: TaskGraphDefinition,
        graph: TaskGraphSnapshot,
        tasks: tuple[TaskSnapshot, ...],
    ) -> TaskGraphSnapshot:
        async with self._lock:
            run_key = (definition.organization_id, definition.agent_run_id)
            existing_id = self._run_index.get(run_key)
            if existing_id is not None:
                existing = self._graphs[existing_id]
                if existing.definition_hash != definition.definition_hash:
                    raise TaskGraphConflictError("TASK_GRAPH_RUN_DEFINITION_CONFLICT")
                return existing
            if graph.graph_id in self._graphs:
                existing = self._graphs[graph.graph_id]
                if existing.definition_hash != definition.definition_hash:
                    raise TaskGraphConflictError("TASK_GRAPH_ID_COLLISION")
                return existing
            task_map = {task.task_id: task for task in tasks}
            if len(task_map) != len(tasks):
                raise TaskGraphConflictError("TASK_GRAPH_TASK_ID_COLLISION")
            self._definitions[graph.graph_id] = definition
            self._graphs[graph.graph_id] = graph
            self._tasks[graph.graph_id] = task_map
            self._events[graph.graph_id] = []
            self._run_index[run_key] = graph.graph_id
            return graph

    async def find_graph_by_run(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
    ) -> TaskGraphSnapshot | None:
        async with self._lock:
            graph_id = self._run_index.get((organization_id, agent_run_id))
            return None if graph_id is None else self._graphs[graph_id]

    @asynccontextmanager
    async def transaction(self, graph_id: UUID) -> AsyncIterator[_MemoryTransaction]:
        async with self._lock:
            if graph_id not in self._graphs:
                raise KeyError(graph_id)
            yield _MemoryTransaction(self, graph_id)

    async def attempts_for_task(self, task_id: UUID) -> tuple[TaskAttempt, ...]:
        async with self._lock:
            values = [
                attempt
                for (candidate, _), attempt in self._attempts.items()
                if candidate == task_id
            ]
            return tuple(sorted(values, key=lambda item: item.attempt_number))

    async def events(self, graph_id: UUID) -> tuple[TaskGraphEvent, ...]:
        async with self._lock:
            return tuple(self._events.get(graph_id, ()))


__all__ = ["InMemoryTaskGraphStore", "TaskGraphStore", "TaskGraphTransaction"]
