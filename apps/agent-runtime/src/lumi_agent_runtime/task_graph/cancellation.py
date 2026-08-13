from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from .contracts_events import TaskGraphEvent
from .errors import TaskGraphLeaseError
from .lifecycle import recompute_graph, refresh_ready_tasks
from .memory_store import InMemoryTaskGraphStore
from .state_machine import assert_transition
from .states import TERMINAL_TASK_STATES, WAITING_TASK_STATES, TaskState
from .task_contracts import TaskSnapshot


def request_graph_cancel(
    store: InMemoryTaskGraphStore,
    graph_id: UUID,
    *,
    now: datetime,
) -> tuple[UUID, ...]:
    graph = store.graph(graph_id)
    if graph.cancellation_requested_at is None:
        store.replace_graph(
            replace(
                graph,
                cancellation_requested_at=now,
                state_version=graph.state_version + 1,
            ),
            expected_version=graph.state_version,
        )
    changed: list[UUID] = []
    for task in store.tasks(graph_id):
        if task.status in TERMINAL_TASK_STATES:
            continue
        if task.status == TaskState.RUNNING:
            updated = replace(
                task,
                cancellation_requested_at=now,
                state_version=task.state_version + 1,
            )
        else:
            assert_transition(task.status, TaskState.CANCELLED)
            updated = replace(
                task,
                status=TaskState.CANCELLED,
                cancellation_requested_at=now,
                completed_at=now,
                wait_reason=None,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                state_version=task.state_version + 1,
            )
        store.replace_task(updated, expected_version=task.state_version)
        store.emit(
            TaskGraphEvent(
                event_name="task.cancel_requested",
                graph_id=graph_id,
                task_id=task.task_id,
                organization_id=task.organization_id,
                payload={"task_key": task.task_key, "running": task.status == TaskState.RUNNING},
            )
        )
        changed.append(task.task_id)
    recompute_graph(store, graph_id, now=now)
    return tuple(changed)


def acknowledge_running_cancel(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    worker_id: str,
    now: datetime,
) -> TaskSnapshot:
    task = store.task(task_id)
    if (
        task.status != TaskState.RUNNING
        or task.lease_owner != worker_id
        or task.cancellation_requested_at is None
    ):
        raise TaskGraphLeaseError("TASK_CANCEL_ACK_INVALID")
    assert_transition(task.status, TaskState.CANCELLED)
    updated = replace(
        task,
        status=TaskState.CANCELLED,
        completed_at=now,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=None,
        state_version=task.state_version + 1,
    )
    store.replace_task(updated, expected_version=task.state_version)
    store.finish_attempt(
        task.task_id,
        task.attempt_count,
        status=TaskState.CANCELLED.value,
        completed_at=now,
        error_category="cancelled",
    )
    store.emit(
        TaskGraphEvent(
            event_name="task.cancelled",
            graph_id=task.graph_id,
            task_id=task.task_id,
            organization_id=task.organization_id,
            payload={"task_key": task.task_key},
        )
    )
    refresh_ready_tasks(store, task.graph_id, now=now)
    recompute_graph(store, task.graph_id, now=now)
    return updated
