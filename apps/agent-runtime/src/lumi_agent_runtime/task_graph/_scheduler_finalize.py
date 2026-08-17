from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from ._scheduler_helpers import _graph_event, _money, _worker
from .contracts import TERMINAL_GRAPH_STATES, TaskGraphState, TaskSnapshot, TaskState
from .errors import TaskGraphLeaseError
from .state_machine import assert_graph_transition, assert_task_transition
from .store import TaskGraphTransaction


class _SchedulerFinalizeMixin:

    def _enter_failure_draining(
        self,
        tx: TaskGraphTransaction,
        *,
        now: datetime,
        error_code: str,
    ) -> None:
        graph = tx.graph()
        if graph.status is not TaskGraphState.FAILURE_DRAINING:
            assert_graph_transition(graph.status, TaskGraphState.FAILURE_DRAINING)
            updated_graph = replace(
                graph,
                status=TaskGraphState.FAILURE_DRAINING,
                error_code=error_code,
                updated_at=now,
                state_version=graph.state_version + 1,
            )
            tx.put_graph(updated_graph, expected_version=graph.state_version)
        for task in tx.tasks():
            if task.terminal:
                continue
            if task.status is TaskState.RUNNING:
                updated = replace(
                    task,
                    cancellation_requested_at=task.cancellation_requested_at or now,
                    state_version=task.state_version + 1,
                )
            else:
                target = (
                    TaskState.SKIPPED
                    if task.status in {TaskState.PENDING, TaskState.READY}
                    else TaskState.CANCELLED
                )
                assert_task_transition(task.status, target)
                updated = replace(
                    task,
                    status=target,
                    error_code="TASK_FAIL_FAST_ABORTED",
                    completed_at=now,
                    state_version=task.state_version + 1,
                )
            tx.put_task(updated, expected_version=task.state_version)

    def _exhaust_budget(self, tx: TaskGraphTransaction, *, now: datetime) -> None:
        graph = tx.graph()
        if (
            graph.status in TERMINAL_GRAPH_STATES
            or graph.status is TaskGraphState.FAILURE_DRAINING
        ):
            return
        self._enter_failure_draining(
            tx,
            now=now,
            error_code="TASK_GRAPH_BUDGET_EXHAUSTED",
        )

    def _fail_budget_task(
        self,
        tx: TaskGraphTransaction,
        task: TaskSnapshot,
        *,
        now: datetime,
    ) -> None:
        assert_task_transition(task.status, TaskState.SKIPPED)
        updated = replace(
            task,
            status=TaskState.SKIPPED,
            error_code="TASK_BUDGET_EXHAUSTED",
            completed_at=now,
            state_version=task.state_version + 1,
        )
        tx.put_task(updated, expected_version=task.state_version)

    def _add_graph_cost(
        self,
        tx: TaskGraphTransaction,
        *,
        cost: Decimal,
        now: datetime,
    ) -> None:
        if cost == 0:
            return
        graph = tx.graph()
        updated = replace(
            graph,
            cost_spent_usd=_money(Decimal(graph.cost_spent_usd) + cost),
            updated_at=now,
            state_version=graph.state_version + 1,
        )
        tx.put_graph(updated, expected_version=graph.state_version)

    def _finish_attempt(
        self,
        tx: TaskGraphTransaction,
        task: TaskSnapshot,
        *,
        status: str,
        now: datetime,
        cost: Decimal,
        error_code: str | None = None,
        result_ref: str | None = None,
    ) -> None:
        attempt = tx.attempt(task.task_id, task.attempt_count)
        tx.replace_attempt(
            replace(
                attempt,
                status=status,
                completed_at=now,
                cost_amount_usd=_money(cost),
                error_code=error_code,
                result_ref=result_ref,
            )
        )

    def _finish_graph(
        self,
        tx: TaskGraphTransaction,
        target: TaskGraphState,
        *,
        now: datetime,
    ) -> None:
        graph = tx.graph()
        if graph.status is target:
            return
        assert_graph_transition(graph.status, target)
        updated = replace(
            graph,
            status=target,
            updated_at=now,
            state_version=graph.state_version + 1,
        )
        tx.put_graph(updated, expected_version=graph.state_version)
        tx.append_event(_graph_event(updated, f"graph.{target.value}", now, {}))

    @staticmethod
    def _assert_active_lease(
        task: TaskSnapshot,
        worker_id: str,
        lease_token: str,
        now: datetime,
    ) -> None:
        _worker(worker_id)
        if task.status is not TaskState.RUNNING:
            raise TaskGraphLeaseError("TASK_LEASE_TASK_NOT_RUNNING")
        if task.lease_owner != worker_id or task.lease_token != lease_token:
            raise TaskGraphLeaseError("TASK_LEASE_FENCING_MISMATCH")
        if task.lease_expires_at is None or task.lease_expires_at < now:
            raise TaskGraphLeaseError("TASK_LEASE_EXPIRED")
