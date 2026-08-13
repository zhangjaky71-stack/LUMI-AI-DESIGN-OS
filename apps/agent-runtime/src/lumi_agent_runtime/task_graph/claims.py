from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from .contracts_events import TaskGraphEvent
from .errors import TaskGraphClaimError, TaskGraphLeaseError
from .memory_store import InMemoryTaskGraphStore
from .state_machine import assert_transition
from .states import TaskState
from .task_contracts import TaskAttempt, TaskSnapshot, operation_key


def claim_ready_tasks(
    store: InMemoryTaskGraphStore,
    graph_id: UUID,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 60,
    limit: int = 1,
) -> tuple[TaskSnapshot, ...]:
    if not worker_id or not 5 <= lease_seconds <= 3600 or not 1 <= limit <= 32:
        raise TaskGraphClaimError("TASK_CLAIM_ARGUMENT_INVALID")
    tasks = store.tasks(graph_id)
    running_by_group: dict[str, int] = {}
    for task in tasks:
        if task.status == TaskState.RUNNING and task.concurrency_group:
            running_by_group[task.concurrency_group] = (
                running_by_group.get(task.concurrency_group, 0) + 1
            )
    candidates = sorted(
        (
            task
            for task in tasks
            if task.status == TaskState.READY
            and task.cancellation_requested_at is None
            and (task.retry_not_before is None or task.retry_not_before <= now)
        ),
        key=lambda item: (-item.priority, item.task_key),
    )
    claimed: list[TaskSnapshot] = []
    for task in candidates:
        if len(claimed) >= limit:
            break
        if task.concurrency_group and task.concurrency_limit is not None:
            active = running_by_group.get(task.concurrency_group, 0)
            if active >= task.concurrency_limit:
                continue
        if task.attempt_count >= task.max_attempts:
            continue
        assert_transition(task.status, TaskState.RUNNING)
        attempt_number = task.attempt_count + 1
        updated = replace(
            task,
            status=TaskState.RUNNING,
            attempt_count=attempt_number,
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            heartbeat_at=now,
            started_at=task.started_at or now,
            retry_not_before=None,
            wait_reason=None,
            external_ref=None,
            state_version=task.state_version + 1,
        )
        store.replace_task(updated, expected_version=task.state_version)
        store.append_attempt(
            TaskAttempt(
                task_id=task.task_id,
                attempt_number=attempt_number,
                operation_key=operation_key(graph_id, task.task_id, attempt_number),
                status="RUNNING",
                started_at=now,
            )
        )
        store.emit(
            TaskGraphEvent(
                event_name="task.started",
                graph_id=graph_id,
                task_id=task.task_id,
                organization_id=task.organization_id,
                payload={
                    "task_key": task.task_key,
                    "attempt": attempt_number,
                    "operation_key": operation_key(
                        graph_id,
                        task.task_id,
                        attempt_number,
                    ),
                },
            )
        )
        claimed.append(updated)
        if task.concurrency_group:
            running_by_group[task.concurrency_group] = (
                running_by_group.get(task.concurrency_group, 0) + 1
            )
    return tuple(claimed)


def heartbeat_task(
    store: InMemoryTaskGraphStore,
    task_id: UUID,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 60,
) -> TaskSnapshot:
    task = store.task(task_id)
    if task.status != TaskState.RUNNING or task.lease_owner != worker_id:
        raise TaskGraphLeaseError("TASK_HEARTBEAT_LEASE_OWNER_MISMATCH")
    if task.lease_expires_at is None or task.lease_expires_at < now:
        raise TaskGraphLeaseError("TASK_HEARTBEAT_LEASE_EXPIRED")
    updated = replace(
        task,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
        state_version=task.state_version + 1,
    )
    return store.replace_task(updated, expected_version=task.state_version)


def reclaim_expired_leases(
    store: InMemoryTaskGraphStore,
    graph_id: UUID,
    *,
    now: datetime,
) -> tuple[UUID, ...]:
    reclaimed: list[UUID] = []
    for task in store.tasks(graph_id):
        if (
            task.status != TaskState.RUNNING
            or task.lease_expires_at is None
            or task.lease_expires_at >= now
        ):
            continue
        if task.attempt_count >= task.max_attempts:
            target = TaskState.FAILED_FINAL
        else:
            target = TaskState.FAILED_RETRYABLE
        assert_transition(task.status, target)
        updated = replace(
            task,
            status=target,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            error={
                "category": "lease_expired",
                "provider_reconciliation_required": True,
            },
            state_version=task.state_version + 1,
        )
        store.replace_task(updated, expected_version=task.state_version)
        store.finish_attempt(
            task.task_id,
            task.attempt_count,
            status=target.value,
            completed_at=now,
            error_category="lease_expired",
        )
        store.emit(
            TaskGraphEvent(
                event_name="task.failed",
                graph_id=graph_id,
                task_id=task.task_id,
                organization_id=task.organization_id,
                payload={
                    "task_key": task.task_key,
                    "status": target.value,
                    "provider_reconciliation_required": True,
                },
            )
        )
        reclaimed.append(task.task_id)
    return tuple(reclaimed)
