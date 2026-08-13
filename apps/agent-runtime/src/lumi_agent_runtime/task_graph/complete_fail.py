from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from .claims import heartbeat_task
from .contracts_events import TaskGraphEvent
from .errors import TaskGraphLeaseError, TaskGraphStateError
from .lifecycle import recompute_graph, refresh_ready_tasks
from .memory_store import InMemoryTaskGraphStore
from .state_machine import assert_transition
from .states import TaskState
from .task_contracts import TaskSnapshot


def complete_task(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    worker_id: str,
    now: datetime,
    output: dict[str, Any],
    result_ref: str | None = None,
    cost_amount_usd: str | None = None,
) -> TaskSnapshot:
    task = _leased_running(store, task_id, worker_id, now)
    assert_transition(task.status, TaskState.SUCCEEDED)
    updated = replace(
        task,
        status=TaskState.SUCCEEDED,
        progress_current=task.progress_total,
        output=dict(output),
        error={},
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
        status=TaskState.SUCCEEDED.value,
        completed_at=now,
        result_ref=result_ref,
        cost_amount_usd=cost_amount_usd,
    )
    _emit(store, updated, "task.succeeded", {"task_key": task.task_key})
    refresh_ready_tasks(store, task.graph_id, now=now)
    recompute_graph(store, task.graph_id, now=now)
    return updated


def fail_task(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    worker_id: str,
    now: datetime,
    retryable: bool,
    error_category: str,
    error: dict[str, Any] | None = None,
) -> TaskSnapshot:
    task = _leased_running(store, task_id, worker_id, now)
    target = (
        TaskState.FAILED_RETRYABLE
        if retryable and task.attempt_count < task.max_attempts
        else TaskState.FAILED_FINAL
    )
    assert_transition(task.status, target)
    payload = dict(error or {})
    payload["category"] = error_category
    updated = replace(
        task,
        status=target,
        error=payload,
        completed_at=now if target == TaskState.FAILED_FINAL else None,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=None,
        state_version=task.state_version + 1,
    )
    store.replace_task(updated, expected_version=task.state_version)
    store.finish_attempt(
        task.task_id,
        task.attempt_count,
        status=target.value,
        completed_at=now,
        error_category=error_category,
    )
    _emit(
        store,
        updated,
        "task.failed",
        {"task_key": task.task_key, "status": target.value, "error_category": error_category},
    )
    if target == TaskState.FAILED_FINAL:
        refresh_ready_tasks(store, task.graph_id, now=now)
    recompute_graph(store, task.graph_id, now=now)
    return updated


def schedule_retry(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    retry_not_before: datetime,
) -> TaskSnapshot:
    task = store.task(task_id)
    if task.status != TaskState.FAILED_RETRYABLE:
        raise TaskGraphStateError("TASK_RETRY_REQUIRES_RETRYABLE_FAILURE")
    assert_transition(task.status, TaskState.READY)
    updated = replace(
        task,
        status=TaskState.READY,
        retry_not_before=retry_not_before,
        completed_at=None,
        state_version=task.state_version + 1,
    )
    store.replace_task(updated, expected_version=task.state_version)
    _emit(
        store,
        updated,
        "task.retry_scheduled",
        {
            "task_key": task.task_key,
            "attempt_count": task.attempt_count,
            "retry_not_before": retry_not_before.isoformat(),
        },
    )
    return updated


def _leased_running(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    worker_id: str,
    now: datetime,
) -> TaskSnapshot:
    task = store.task(task_id)
    if task.status != TaskState.RUNNING or task.lease_owner != worker_id:
        raise TaskGraphLeaseError("TASK_COMPLETION_LEASE_OWNER_MISMATCH")
    if task.lease_expires_at is None or task.lease_expires_at < now:
        raise TaskGraphLeaseError("TASK_COMPLETION_LEASE_EXPIRED")
    return task


def _emit(
    store: InMemoryTaskGraphStore,
    task: TaskSnapshot,
    event_name: str,
    payload: dict[str, Any],
) -> None:
    store.emit(
        TaskGraphEvent(
            event_name=event_name,
            graph_id=task.graph_id,
            task_id=task.task_id,
            organization_id=task.organization_id,
            payload=payload,
        )
    )
