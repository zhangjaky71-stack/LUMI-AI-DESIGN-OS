from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from lumi_agent_runtime.recipe_engine.expression import evaluate_expression

from .events import TaskGraphEvent
from .graph_contracts import TaskGraphSnapshot
from .memory_store import InMemoryTaskGraphStore
from .state_machine import assert_transition
from .states import TERMINAL_TASK_STATES, WAITING_TASK_STATES, TaskGraphState, TaskState
from .task_contracts import TaskSnapshot


def refresh_ready_tasks(
    store: InMemoryTaskGraphStore,
    graph_id: UUID,
    *,
    now: datetime,
    condition_context: dict[str, Any] | None = None,
) -> tuple[UUID, ...]:
    tasks = store.tasks(graph_id)
    by_id = {item.task_id: item for item in tasks}
    changed: list[UUID] = []
    for task in tasks:
        if task.status != TaskState.PENDING:
            continue
        dependencies = [by_id[item] for item in task.depends_on]
        decision = _join_decision(task, dependencies)
        if decision == "pending":
            continue
        if decision == "impossible":
            _skip_task(store, task, now=now, reason="UPSTREAM_JOIN_UNSATISFIED")
            changed.append(task.task_id)
            continue
        if task.condition is not None:
            context = _condition_context(tasks, condition_context)
            if not evaluate_expression(task.condition, context):
                _skip_task(store, task, now=now, reason="CONDITION_FALSE")
                changed.append(task.task_id)
                continue
        assert_transition(task.status, TaskState.READY)
        updated = replace(task, status=TaskState.READY, state_version=task.state_version + 1)
        store.replace_task(updated, expected_version=task.state_version)
        store.emit(TaskGraphEvent(event_name="task.ready", graph_id=graph_id, task_id=task.task_id, organization_id=task.organization_id, payload={"task_key": task.task_key}))
        changed.append(task.task_id)
    recompute_graph(store, graph_id, now=now)
    return tuple(changed)


def recompute_graph(store: InMemoryTaskGraphStore, graph_id: UUID, *, now: datetime) -> TaskGraphSnapshot:
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
    elif any(item.status in WAITING_TASK_STATES for item in tasks) and not any(item.status in {TaskState.READY, TaskState.RUNNING} for item in tasks):
        status = TaskGraphState.WAITING
        completed_at = None
    else:
        status = TaskGraphState.RUNNING
        completed_at = None
    changed = graph.status != status or graph.completed_count != completed or graph.succeeded_count != succeeded or graph.failed_count != failed or graph.cancelled_count != cancelled or graph.skipped_count != skipped or graph.completed_at != completed_at
    if not changed:
        return graph
    updated = replace(graph, status=status, completed_count=completed, succeeded_count=succeeded, failed_count=failed, cancelled_count=cancelled, skipped_count=skipped, completed_at=completed_at, state_version=graph.state_version + 1)
    store.replace_graph(updated, expected_version=graph.state_version)
    if status in {TaskGraphState.SUCCEEDED, TaskGraphState.FAILED_FINAL, TaskGraphState.CANCELLED}:
        store.emit(TaskGraphEvent(event_name="task_graph.completed", graph_id=graph_id, task_id=None, organization_id=graph.organization_id, payload={"status": status.value, "completed_count": completed, "task_count": len(tasks)}))
    return updated


def _join_decision(task: TaskSnapshot, dependencies: list[TaskSnapshot]) -> str:
    if not dependencies:
        return "ready"
    policy = str(task.metadata.get("join_policy", "ALL")).upper()
    successes = sum(item.status == TaskState.SUCCEEDED for item in dependencies)
    terminal = sum(item.status in TERMINAL_TASK_STATES for item in dependencies)
    if policy == "ANY":
        if successes >= 1:
            return "ready"
        return "impossible" if terminal == len(dependencies) else "pending"
    if policy == "MIN_SUCCESS":
        raw = task.metadata.get("min_success")
        minimum = raw if isinstance(raw, int) and not isinstance(raw, bool) else len(dependencies)
        if not 1 <= minimum <= len(dependencies):
            return "impossible"
        if successes >= minimum:
            return "ready"
        return "impossible" if successes + (len(dependencies) - terminal) < minimum else "pending"
    if policy == "ALL":
        if successes == len(dependencies):
            return "ready"
        if any(item.status in {TaskState.FAILED_FINAL, TaskState.CANCELLED, TaskState.SKIPPED} for item in dependencies):
            return "impossible"
        return "pending"
    return "impossible"


def _condition_context(tasks: tuple[TaskSnapshot, ...], supplied: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(supplied or {})
    context = {"inputs": dict(base.get("inputs", {})), "project": dict(base.get("project", {})), "run": dict(base.get("run", {})), "steps": dict(base.get("steps", {}))}
    for item in tasks:
        if item.output:
            context["steps"][item.task_key] = dict(item.output)
    return context


def _skip_task(store: InMemoryTaskGraphStore, task: TaskSnapshot, *, now: datetime, reason: str) -> None:
    assert_transition(task.status, TaskState.SKIPPED)
    updated = replace(task, status=TaskState.SKIPPED, completed_at=now, error={"reason": reason}, state_version=task.state_version + 1)
    store.replace_task(updated, expected_version=task.state_version)
    store.emit(TaskGraphEvent(event_name="task.skipped", graph_id=task.graph_id, task_id=task.task_id, organization_id=task.organization_id, payload={"task_key": task.task_key, "reason": reason}))
