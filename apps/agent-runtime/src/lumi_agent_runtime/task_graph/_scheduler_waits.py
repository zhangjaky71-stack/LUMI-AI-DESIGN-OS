from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ._scheduler_helpers import _aware, _event, _graph_event
from .contracts import (
    TaskGraphSnapshot,
    TaskGraphState,
    TaskSnapshot,
    TaskState,
    TERMINAL_GRAPH_STATES,
    WAITING_TASK_STATES,
)
from .errors import TaskGraphStateError
from .state_machine import assert_graph_transition, assert_task_transition


class _SchedulerWaitsMixin:

    async def suspend(
        self,
        graph_id: UUID,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime,
        wait_ref: str,
        waiting_state: TaskState,
    ) -> TaskSnapshot:
        if waiting_state not in WAITING_TASK_STATES:
            raise ValueError("TASK_WAIT_STATE_INVALID")
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            task = tx.task(task_id)
            self._assert_active_lease(task, worker_id, lease_token, now)
            assert_task_transition(task.status, waiting_state)
            updated = replace(
                task,
                status=waiting_state,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                wait_ref=wait_ref,
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            self._finish_attempt(
                tx,
                updated,
                status=waiting_state.value,
                now=now,
                cost=Decimal("0"),
            )
            tx.append_event(_event(updated, "task.waiting", now, {"wait_ref": wait_ref}))
            self._recompute_graph(tx, now=now)
            return updated

    async def resolve_wait(
        self,
        graph_id: UUID,
        task_id: UUID,
        *,
        now: datetime,
        succeeded: bool,
        result_ref: str | None = None,
        error_code: str | None = None,
    ) -> TaskSnapshot:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            task = tx.task(task_id)
            if task.status not in WAITING_TASK_STATES:
                raise TaskGraphStateError("TASK_NOT_WAITING")
            target = TaskState.SUCCEEDED if succeeded else TaskState.FAILED_FINAL
            assert_task_transition(task.status, target)
            updated = replace(
                task,
                status=target,
                wait_ref=None,
                output_ref=result_ref if succeeded else None,
                error_code=None if succeeded else (error_code or "TASK_WAIT_FAILED"),
                completed_at=now,
                state_version=task.state_version + 1,
            )
            tx.put_task(updated, expected_version=task.state_version)
            tx.append_event(
                _event(updated, "task.wait_resolved", now, {"succeeded": succeeded})
            )
            self._recompute_graph(tx, now=now)
            return updated

    async def reclaim_expired(self, graph_id: UUID, *, now: datetime) -> tuple[UUID, ...]:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            reclaimed = self._reclaim_expired_locked(tx, now=now)
            self._recompute_graph(tx, now=now)
            return reclaimed

    async def pause(self, graph_id: UUID, *, now: datetime) -> TaskGraphSnapshot:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            graph = tx.graph()
            if graph.status is TaskGraphState.PAUSED:
                return graph
            if graph.status in TERMINAL_GRAPH_STATES or graph.status in {
                TaskGraphState.CANCEL_REQUESTED,
                TaskGraphState.FAILURE_DRAINING,
            }:
                raise TaskGraphStateError("TASK_GRAPH_PAUSE_INVALID")
            assert_graph_transition(graph.status, TaskGraphState.PAUSED)
            updated = replace(
                graph,
                status=TaskGraphState.PAUSED,
                pause_requested_at=now,
                updated_at=now,
                state_version=graph.state_version + 1,
            )
            tx.put_graph(updated, expected_version=graph.state_version)
            tx.append_event(_graph_event(updated, "graph.paused", now, {}))
            return updated

    async def resume(self, graph_id: UUID, *, now: datetime) -> TaskGraphSnapshot:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            graph = tx.graph()
            if graph.status is not TaskGraphState.PAUSED:
                raise TaskGraphStateError("TASK_GRAPH_RESUME_INVALID")
            assert_graph_transition(graph.status, TaskGraphState.RUNNING)
            updated = replace(
                graph,
                status=TaskGraphState.RUNNING,
                pause_requested_at=None,
                updated_at=now,
                state_version=graph.state_version + 1,
            )
            tx.put_graph(updated, expected_version=graph.state_version)
            tx.append_event(_graph_event(updated, "graph.resumed", now, {}))
            self._promote_ready(tx, now=now)
            self._recompute_graph(tx, now=now)
            return tx.graph()

    async def cancel(self, graph_id: UUID, *, now: datetime) -> TaskGraphSnapshot:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            graph = tx.graph()
            if graph.status is TaskGraphState.CANCELLED:
                return graph
            if graph.status in {TaskGraphState.SUCCEEDED, TaskGraphState.FAILED_FINAL}:
                raise TaskGraphStateError("TASK_GRAPH_CANCEL_TERMINAL")
            if graph.status is not TaskGraphState.CANCEL_REQUESTED:
                assert_graph_transition(graph.status, TaskGraphState.CANCEL_REQUESTED)
                graph = replace(
                    graph,
                    status=TaskGraphState.CANCEL_REQUESTED,
                    cancellation_requested_at=now,
                    updated_at=now,
                    state_version=graph.state_version + 1,
                )
                tx.put_graph(graph, expected_version=graph.state_version - 1)
                tx.append_event(_graph_event(graph, "graph.cancel_requested", now, {}))
            for task in tx.tasks():
                if task.terminal:
                    continue
                if task.status is TaskState.RUNNING:
                    updated_task = replace(
                        task,
                        cancellation_requested_at=task.cancellation_requested_at or now,
                        state_version=task.state_version + 1,
                    )
                else:
                    assert_task_transition(task.status, TaskState.CANCELLED)
                    updated_task = replace(
                        task,
                        status=TaskState.CANCELLED,
                        cancellation_requested_at=task.cancellation_requested_at or now,
                        completed_at=now,
                        state_version=task.state_version + 1,
                    )
                tx.put_task(updated_task, expected_version=task.state_version)
            self._recompute_graph(tx, now=now)
            return tx.graph()
