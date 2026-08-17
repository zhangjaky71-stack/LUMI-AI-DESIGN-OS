from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ._scheduler_helpers import _aware, _money, _task_snapshot
from .contracts import (
    TaskGraphDefinition,
    TaskGraphSnapshot,
    TaskGraphState,
    TaskSnapshot,
    TERMINAL_GRAPH_STATES,
)
from .errors import TaskGraphConflictError


class _SchedulerCoreMixin:

    async def ensure_graph(
        self,
        definition: TaskGraphDefinition,
        *,
        now: datetime,
    ) -> TaskGraphSnapshot:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        existing = await self.store.find_graph_by_run(
            organization_id=definition.organization_id,
            agent_run_id=definition.agent_run_id,
        )
        if existing is not None:
            if existing.definition_hash != definition.definition_hash:
                raise TaskGraphConflictError("TASK_GRAPH_RUN_DEFINITION_CONFLICT")
            return existing

        graph = TaskGraphSnapshot(
            graph_id=definition.graph_id,
            organization_id=definition.organization_id,
            project_id=definition.project_id,
            agent_run_id=definition.agent_run_id,
            graph_key=definition.graph_key,
            exact_version=definition.exact_version,
            definition_hash=definition.definition_hash,
            status=TaskGraphState.RUNNING,
            budget_limit_usd=_money(Decimal(definition.budget_limit_usd)),
            cost_spent_usd="0.000000",
            max_parallelism=definition.max_parallelism,
            failure_mode=definition.failure_mode,
            created_at=now,
            updated_at=now,
        )
        by_key = {task.task_key: task for task in definition.tasks}
        snapshots = tuple(
            _task_snapshot(definition, task, by_key, now=now)
            for task in definition.tasks
        )
        created = await self.store.create_graph(definition, graph, snapshots)
        await self.refresh_ready(created.graph_id, now=now)
        return await self.graph(created.graph_id)

    async def graph(self, graph_id: UUID) -> TaskGraphSnapshot:
        async with self.store.transaction(graph_id) as tx:
            return tx.graph()

    async def tasks(self, graph_id: UUID) -> tuple[TaskSnapshot, ...]:
        async with self.store.transaction(graph_id) as tx:
            return tx.tasks()

    async def refresh_ready(self, graph_id: UUID, *, now: datetime) -> tuple[UUID, ...]:
        _aware(now, "TASK_GRAPH_NOW_INVALID")
        async with self.store.transaction(graph_id) as tx:
            graph = tx.graph()
            if graph.status in TERMINAL_GRAPH_STATES or graph.status in {
                TaskGraphState.PAUSED,
                TaskGraphState.CANCEL_REQUESTED,
                TaskGraphState.FAILURE_DRAINING,
            }:
                return ()
            changed = self._promote_ready(tx, now=now)
            self._recompute_graph(tx, now=now)
            return changed
