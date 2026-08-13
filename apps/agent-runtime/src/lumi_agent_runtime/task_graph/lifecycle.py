from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from .contracts_events import TaskGraphEvent
from .graph_contracts import TaskGraphSnapshot
from .memory_store import InMemoryTaskGraphStore
from .state_machine import assert_transition
from .states import TERMINAL_TASK_STATES, WAITING_TASK_STATES, TaskGraphState, TaskState


def refresh_ready_tasks(
    store: InMemoryTaskGraphStore,
    graph_id: UUID,
    *,
    now: datetime,
) -> tuple[UUID, ...]:
    tasks = store.tasks(graph_id)
    by_id = {item.task_id: item for item in tasks}
    changed: list[UUID] = []
    for task in tasks:
        if task.status != TaskState.PENDING:
            continue
        dependencies = [by_id[item] for item in task.depends_on]
        if any(
            dependency.status in {
                TaskState.FAILED_FINAL,
                TaskState.CANCELLED,
                TaskState.SKIPPED,
            }
            for dependency in dependencies
        ):
            assert_transition(task.status, TaskState.SKIPPED)
            updated = replace(
                task,
                status=TaskState.SKIPPED,
                completed_at=now,
                state_version=task.state_version + 1,
                error={"reason": "UPSTREAM_TERMINAL_NON_SUCCESS"},
            )
            store.replace_task(updated, expected_version=task.state_version)
            store.emit(
                TaskGraphEvent(
                    event_name="task.skipped",
                    graph_id=graph_id,
                    task_id=task.task_id,
                    organization_id=task.organization_id,
                    payload={"task_key": task.task_key},
                )
            )
            changed.append(task.task_id)
            continue
        if all(dependency.status == TaskState.SUCCEEDED for dependency in dependencies):
            assert_transition(task.status, TaskState.READY)
            updated = replace(
                task,
                status=TaskState.READY,
                state_version=task.state_version + 1,
            )
            store.replace_task(updated, expected_version=task.state_version)
            store.emit(
                TaskGraphEvent(
                    event_name="task.ready",
                    graph_id=graph_id,
                    task_id=task.task_id,
                    organization_id=task.organization_id,
                    payload={"task_key": task.task_key},
                )
            )
            changed.append(task.task_id)
    recompute_graph(store, graph_id, now=now)
    return tuple(changed)


def recompute_graph(
    store: InMemoryTaskGraphStore,
    graph_id: UUID,
    *,
    now: datetime,
) -> TaskGraphSnapshot:
    graph = store.graph(graph_id)
    tasks = store.tasks(graph_id)
    completed = sum(item.status in TERMINAL_TASK_STATES for item in tasks)
    succeeded = sum(item.status == TaskState.SUCCEEDED for item in tasks)
    failed = sum(item.status == TaskState.FAILED_FINAL for item in tasks)
    cancelled = sum(item.status == TaskState.CANCELLED for item in tasks)
    skipped = sum(item.status == TaskState.SKIPPED for item in tasks)
    if completed == len(tasks):
        if failed:
            status = TaskGraphState.FAILED_FINAL
        elif cancelled and graph.cancellation_requested_at is not None:
            status = TaskGraphState.CANCELLED
        else:
            status = TaskGraphState.SUCCEEDED
        completed_at = graph.completed_at or now
    elif any(item.status in WAITING_TASK_STATES for item in tasks) and not any(
        item.status in {TaskState.READY, TaskState.RUNNING} for item in tasks
    ):
        status = TaskGraphState.WAITING
        completed_at = None
    else:
        status = TaskGraphState.RUNNING
        completed_at = None
    changed = (
        graph.status != status
        or graph.completed_count != completed
        or graph.succeeded_count != succeeded
        or graph.failed_count != failed
        or graph.cancelled_count != cancelled
        or graph.skipped_count != skipped
        or graph.completed_at != completed_at
    )
    if not changed:
        return graph
    updated = replace(
        graph,
        status=status,
        completed_count=completed,
        succeeded_count=succeeded,
        failed_count=failed,
        cancelled_count=cancelled,
        skipped_count=skipped,
        completed_at=completed_at,
        state_version=graph.state_version + 1,
    )
    store.replace_graph(updated, expected_version=graph.state_version)
    if status in {
        TaskGraphState.SUCCEEDED,
        TaskGraphState.FAILED_FINAL,
        TaskGraphState.CANCELLED,
    }:
        store.emit(
            TaskGraphEvent(
                event_name="task_graph.completed",
                graph_id=graph_id,
                task_id=None,
                organization_id=graph.organization_id,
                payload={
                    "status": status.value,
                    "completed_count": completed,
                    "task_count": len(tasks),
                },
            )
        )
    return updated
