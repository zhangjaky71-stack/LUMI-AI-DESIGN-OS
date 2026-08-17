from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from ._scheduler_helpers import _aware, _cost, _event, _money, _worker
from .contracts import (
    TaskAttempt,
    TaskGraphState,
    TaskLease,
    TaskSnapshot,
    TaskState,
    TERMINAL_GRAPH_STATES,
)
from .errors import TaskGraphBudgetError
from .state_machine import assert_task_transition


class _SchedulerClaimsMixin:

    async def claim_ready(
        self,
        graph_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 60,
        limit: int = 1,
    ) -> tuple[TaskLease, ...]:
        _worker(worker_id)
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("TASK_LEASE_SECONDS_INVALID")
        if not 1 <= limit <= 64:
            raise ValueError("TASK_CLAIM_LIMIT_INVALID")

        async with self.store.transaction(graph_id) as tx:
            self._reclaim_expired_locked(tx, now=now)
            graph = tx.graph()
            if graph.status in TERMINAL_GRAPH_STATES:
                return ()
            if graph.status in {
                TaskGraphState.PAUSED,
                TaskGraphState.CANCEL_REQUESTED,
                TaskGraphState.FAILURE_DRAINING,
            }:
                return ()
            self._promote_ready(tx, now=now)
            graph = tx.graph()
            if Decimal(graph.budget_remaining_usd) <= 0:
                self._exhaust_budget(tx, now=now)
                raise TaskGraphBudgetError("TASK_GRAPH_BUDGET_EXHAUSTED")

            tasks = tx.tasks()
            running = [task for task in tasks if task.status is TaskState.RUNNING]
            capacity = max(0, graph.max_parallelism - len(running))
            if capacity == 0:
                return ()
            group_running: dict[str, int] = {}
            for task in running:
                if task.concurrency_group is not None:
                    group_running[task.concurrency_group] = (
                        group_running.get(task.concurrency_group, 0) + 1
                    )
            candidates = sorted(
                (
                    task
                    for task in tasks
                    if task.status is TaskState.READY
                    and task.cancellation_requested_at is None
                    and task.attempt_count < task.retry.max_attempts
                ),
                key=lambda item: (-item.priority, item.task_key),
            )
            leases: list[TaskLease] = []
            for task in candidates:
                if len(leases) >= min(limit, capacity):
                    break
                if task.budget_limit_usd is not None:
                    if Decimal(task.cost_spent_usd) >= Decimal(task.budget_limit_usd):
                        self._fail_budget_task(tx, task, now=now)
                        continue
                if task.concurrency_group is not None:
                    group = task.concurrency_group
                    group_limit = int(task.concurrency_limit or 1)
                    if group_running.get(group, 0) >= group_limit:
                        continue
                assert_task_transition(task.status, TaskState.RUNNING)
                token = str(uuid4())
                expires = now + timedelta(seconds=lease_seconds)
                updated = replace(
                    task,
                    status=TaskState.RUNNING,
                    attempt_count=task.attempt_count + 1,
                    lease_owner=worker_id,
                    lease_token=token,
                    lease_expires_at=expires,
                    heartbeat_at=now,
                    retry_not_before=None,
                    wait_ref=None,
                    error_code=None,
                    started_at=task.started_at or now,
                    state_version=task.state_version + 1,
                )
                tx.put_task(updated, expected_version=task.state_version)
                tx.append_attempt(
                    TaskAttempt(
                        task_id=task.task_id,
                        attempt_number=updated.attempt_count,
                        worker_id=worker_id,
                        lease_token=token,
                        logical_operation_key=task.logical_operation_key,
                        status="running",
                        started_at=now,
                    )
                )
                tx.append_event(
                    _event(updated, "task.started", now, {"attempt": updated.attempt_count})
                )
                leases.append(
                    TaskLease(
                        task=updated,
                        worker_id=worker_id,
                        lease_token=token,
                        lease_expires_at=expires,
                    )
                )
                if task.concurrency_group is not None:
                    group_running[task.concurrency_group] = (
                        group_running.get(task.concurrency_group, 0) + 1
                    )
            self._recompute_graph(tx, now=now)
            return tuple(leases)

    async def heartbeat(
        self,
        task_id: UUID,
        *,
        graph_id: UUID,
        worker_id: str,
        lease_token: str,
        now: datetime,
        lease_seconds: int = 60,
    ) -> TaskSnapshot:
        _worker(worker_id)
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("TASK_LEASE_SECONDS_INVALID")
        async with self.store.transaction(graph_id) as tx:
            task = tx.task(task_id)
            self._assert_active_lease(task, worker_id, lease_token, now)
            updated = replace(
                task,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            return updated

    async def complete(
        self,
        graph_id: UUID,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime,
        cost_amount_usd: str = "0",
        result_ref: str | None = None,
    ) -> TaskSnapshot:
        cost = _cost(cost_amount_usd)
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            task = tx.task(task_id)
            self._assert_active_lease(task, worker_id, lease_token, now)
            assert_task_transition(task.status, TaskState.SUCCEEDED)
            updated = replace(
                task,
                status=TaskState.SUCCEEDED,
                cost_spent_usd=_money(Decimal(task.cost_spent_usd) + cost),
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                output_ref=result_ref,
                error_code=None,
                completed_at=now,
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            self._finish_attempt(
                tx,
                updated,
                status="succeeded",
                now=now,
                cost=cost,
                result_ref=result_ref,
            )
            self._add_graph_cost(tx, cost=cost, now=now)
            tx.append_event(_event(updated, "task.succeeded", now, {"result_ref": result_ref}))
            self._recompute_graph(tx, now=now)
            return updated

    async def fail(
        self,
        graph_id: UUID,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime,
        retryable: bool,
        error_code: str,
        cost_amount_usd: str = "0",
    ) -> TaskSnapshot:
        if not error_code or len(error_code) > 200:
            raise ValueError("TASK_ERROR_CODE_INVALID")
        cost = _cost(cost_amount_usd)
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            task = tx.task(task_id)
            self._assert_active_lease(task, worker_id, lease_token, now)
            can_retry = retryable and task.attempt_count < task.retry.max_attempts
            target = TaskState.FAILED_RETRYABLE if can_retry else TaskState.FAILED_FINAL
            assert_task_transition(task.status, target)
            retry_at = (
                now + timedelta(seconds=task.retry.delay_seconds(task.attempt_count))
                if can_retry
                else None
            )
            updated = replace(
                task,
                status=target,
                cost_spent_usd=_money(Decimal(task.cost_spent_usd) + cost),
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                retry_not_before=retry_at,
                error_code=error_code,
                completed_at=None if can_retry else now,
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            self._finish_attempt(
                tx,
                updated,
                status=target.value,
                now=now,
                cost=cost,
                error_code=error_code,
            )
            self._add_graph_cost(tx, cost=cost, now=now)
            tx.append_event(
                _event(
                    updated,
                    "task.failed",
                    now,
                    {"retryable": can_retry, "error_code": error_code},
                )
            )
            self._recompute_graph(tx, now=now)
            return updated
