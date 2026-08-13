from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from .errors import TaskGraphLeaseError, TaskGraphStateError
from .events import TaskGraphEvent
from .lifecycle import recompute_graph
from .memory_store import InMemoryTaskGraphStore
from .state_machine import assert_transition
from .states import WAITING_TASK_STATES, TaskState
from .task_contracts import TaskSnapshot


def wait_task(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    worker_id: str,
    now: datetime,
    target: TaskState,
    reason: str,
    external_ref: str | None = None,
) -> TaskSnapshot:
    if target not in WAITING_TASK_STATES:
        raise TaskGraphStateError("TASK_WAIT_TARGET_INVALID")
    task = _leased_running(store, task_id, worker_id, now)
    assert_transition(task.status, target)
    updated = replace(
        task,
        status=target,
        wait_reason=reason,
        external_ref=external_ref,
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
    )
    _emit(
        store,
        updated,
        "task.waiting",
        {
            "task_key": task.task_key,
            "status": target.value,
            "reason": reason,
            "external_ref": external_ref,
        },
    )
    recompute_graph(store, task.graph_id, now=now)
    return updated


def resume_waiting_task(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    now: datetime,
    resume_ref: str,
) -> TaskSnapshot:
    task = store.task(task_id)
    if task.status not in WAITING_TASK_STATES:
        raise TaskGraphStateError("TASK_RESUME_REQUIRES_WAITING_STATE")
    assert_transition(task.status, TaskState.READY)
    updated = replace(
        task,
        status=TaskState.READY,
        wait_reason=None,
        external_ref=resume_ref,
        state_version=task.state_version + 1,
    )
    store.replace_task(updated, expected_version=task.state_version)
    _emit(
        store,
        updated,
        "task.ready",
        {"task_key": task.task_key, "resume_ref": resume_ref},
    )
    recompute_graph(store, task.graph_id, now=now)
    return updated


def update_progress(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    worker_id: str,
    now: datetime,
    current: int,
    total: int,
) -> TaskSnapshot:
    task = _leased_running(store, task_id, worker_id, now)
    if total < 1 or current < task.progress_current or current > total:
        raise TaskGraphStateError("TASK_PROGRESS_NON_MONOTONIC")
    updated = replace(
        task,
        progress_current=current,
        progress_total=total,
        state_version=task.state_version + 1,
    )
    store.replace_task(updated, expected_version=task.state_version)
    _emit(
        store,
        updated,
        "task.progress",
        {"task_key": task.task_key, "current": current, "total": total},
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
        raise TaskGraphLeaseError("TASK_LEASE_OWNER_MISMATCH")
    if task.lease_expires_at is None or task.lease_expires_at < now:
        raise TaskGraphLeaseError("TASK_LEASE_EXPIRED")
    return task


def _emit(
    store: InMemoryTaskGraphStore,
    task: TaskSnapshot,
    event_name: str,
    payload: dict[str, object],
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
