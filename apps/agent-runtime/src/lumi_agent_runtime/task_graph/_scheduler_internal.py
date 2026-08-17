from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ._scheduler_helpers import _event, _join_decision
from .contracts import (
    FailureMode,
    TaskGraphState,
    TaskState,
    TERMINAL_GRAPH_STATES,
    TERMINAL_TASK_STATES,
    WAITING_TASK_STATES,
)
from .state_machine import assert_graph_transition, assert_task_transition
from .store import TaskGraphTransaction


class _SchedulerInternalMixin:

    def _promote_ready(self, tx: TaskGraphTransaction, *, now: datetime) -> tuple[UUID, ...]:
        tasks = tx.tasks()
        by_id = {task.task_id: task for task in tasks}
        changed: list[UUID] = []
        for task in tasks:
            if task.status is TaskState.FAILED_RETRYABLE:
                if task.retry_not_before is not None and task.retry_not_before > now:
                    continue
                assert_task_transition(task.status, TaskState.READY)
                updated = replace(
                    task,
                    status=TaskState.READY,
                    retry_not_before=None,
                    state_version=task.state_version + 1,
                )
                tx.put_task(updated, expected_version=task.state_version)
                changed.append(task.task_id)
                by_id[task.task_id] = updated
                continue
            if task.status is not TaskState.PENDING:
                continue
            dependencies = [by_id[item] for item in task.depends_on]
            decision = _join_decision(task.join_policy, dependencies)
            if decision == "pending":
                continue
            if decision == "impossible":
                assert_task_transition(task.status, TaskState.SKIPPED)
                updated = replace(
                    task,
                    status=TaskState.SKIPPED,
                    error_code="TASK_UPSTREAM_UNSATISFIED",
                    completed_at=now,
                    state_version=task.state_version + 1,
                )
                tx.put_task(updated, expected_version=task.state_version)
                tx.append_event(
                    _event(
                        updated,
                        "task.skipped",
                        now,
                        {"reason": updated.error_code},
                    )
                )
                changed.append(task.task_id)
                by_id[task.task_id] = updated
                continue
            assert_task_transition(task.status, TaskState.READY)
            updated = replace(
                task,
                status=TaskState.READY,
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            tx.append_event(_event(updated, "task.ready", now, {}))
            changed.append(task.task_id)
            by_id[task.task_id] = updated
        return tuple(changed)

    def _reclaim_expired_locked(
        self,
        tx: TaskGraphTransaction,
        *,
        now: datetime,
    ) -> tuple[UUID, ...]:
        reclaimed: list[UUID] = []
        for task in tx.tasks():
            if (
                task.status is not TaskState.RUNNING
                or task.lease_expires_at is None
                or task.lease_expires_at >= now
            ):
                continue
            can_retry = task.attempt_count < task.retry.max_attempts
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
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                retry_not_before=retry_at,
                error_code="TASK_LEASE_EXPIRED",
                completed_at=None if can_retry else now,
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            self._finish_attempt(
                tx,
                updated,
                status=target.value,
                now=now,
                cost=Decimal("0"),
                error_code="TASK_LEASE_EXPIRED",
            )
            tx.append_event(
                _event(
                    updated,
                    "task.lease_expired",
                    now,
                    {"provider_reconciliation_required": True},
                )
            )
            reclaimed.append(task.task_id)
        return tuple(reclaimed)

    def _recompute_graph(self, tx: TaskGraphTransaction, *, now: datetime) -> None:
        graph = tx.graph()
        tasks = tx.tasks()
        if graph.status in TERMINAL_GRAPH_STATES:
            return

        if (
            Decimal(graph.cost_spent_usd) >= Decimal(graph.budget_limit_usd)
            and any(task.status not in TERMINAL_TASK_STATES for task in tasks)
        ):
            self._exhaust_budget(tx, now=now)
            graph = tx.graph()
            tasks = tx.tasks()

        failed = [task for task in tasks if task.status is TaskState.FAILED_FINAL]
        running = [task for task in tasks if task.status is TaskState.RUNNING]
        if failed and graph.failure_mode is FailureMode.FAIL_FAST and graph.status not in {
            TaskGraphState.FAILURE_DRAINING,
            TaskGraphState.CANCEL_REQUESTED,
        }:
            self._enter_failure_draining(tx, now=now, error_code="TASK_GRAPH_FAIL_FAST")
            graph = tx.graph()
            tasks = tx.tasks()
            running = [task for task in tasks if task.status is TaskState.RUNNING]

        if graph.status is TaskGraphState.CANCEL_REQUESTED:
            if not running:
                self._finish_graph(tx, TaskGraphState.CANCELLED, now=now)
            return
        if graph.status is TaskGraphState.FAILURE_DRAINING:
            if not running:
                self._finish_graph(tx, TaskGraphState.FAILED_FINAL, now=now)
            return

        if all(task.status in TERMINAL_TASK_STATES for task in tasks):
            target = TaskGraphState.FAILED_FINAL if failed else TaskGraphState.SUCCEEDED
            self._finish_graph(tx, target, now=now)
            return

        if graph.status is TaskGraphState.PAUSED:
            return
        has_ready_or_running = any(
            task.status in {TaskState.READY, TaskState.RUNNING, TaskState.FAILED_RETRYABLE}
            for task in tasks
        )
        has_wait = any(task.status in WAITING_TASK_STATES for task in tasks)
        target = (
            TaskGraphState.WAITING
            if has_wait and not has_ready_or_running
            else TaskGraphState.RUNNING
        )
        if target is not graph.status:
            assert_graph_transition(graph.status, target)
            updated = replace(
                graph,
                status=target,
                updated_at=now,
                state_version=graph.state_version + 1,
            )
            tx.put_graph(updated, expected_version=graph.state_version)
