from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from lumi_agent_runtime.recipe_engine.expression import evaluate_expression

from .errors import TaskGraphConflictError
from .lifecycle import _condition_context, _join_decision
from .postgres_store import PostgresTaskGraphStore, _recompute_graph_locked
from .states import TaskState
from .task_contracts import TaskSnapshot


class DurableTaskGraphScheduler:
    """Recoverable scheduler that promotes durable PENDING tasks before claim."""

    def __init__(self, store: PostgresTaskGraphStore) -> None:
        self.store = store

    async def refresh_ready(
        self,
        graph_id: UUID,
        *,
        now: datetime,
        condition_context: dict[str, Any] | None = None,
    ) -> tuple[UUID, ...]:
        tasks = tuple(_row_to_task(row) for row in await self.store.list_tasks(graph_id))
        by_id = {task.task_id: task for task in tasks}
        changed: list[UUID] = []
        for task in tasks:
            if task.status != TaskState.PENDING:
                continue
            dependencies = [by_id[item] for item in task.depends_on]
            decision = _join_decision(task, dependencies)
            if decision == "pending":
                continue
            if decision == "impossible":
                if await self._skip(task, now=now, reason="UPSTREAM_JOIN_UNSATISFIED"):
                    changed.append(task.task_id)
                continue
            if task.condition is not None and not evaluate_expression(
                task.condition,
                _condition_context(tasks, condition_context),
            ):
                if await self._skip(task, now=now, reason="CONDITION_FALSE"):
                    changed.append(task.task_id)
                continue
            try:
                await self.store.mark_ready(
                    task.task_id,
                    expected_version=task.state_version,
                    expected_status=TaskState.PENDING.value,
                )
            except TaskGraphConflictError:
                continue
            changed.append(task.task_id)
        return tuple(changed)

    async def run_once(
        self,
        graph_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 60,
        claim_limit: int = 1,
        condition_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        await self.store.reclaim_expired(graph_id, now=now)
        await self.refresh_ready(
            graph_id,
            now=now,
            condition_context=condition_context,
        )
        return await self.store.claim_ready(
            graph_id,
            worker_id=worker_id,
            now=now,
            lease_seconds=lease_seconds,
            limit=claim_limit,
        )

    async def _skip(
        self,
        task: TaskSnapshot,
        *,
        now: datetime,
        reason: str,
    ) -> bool:
        try:
            await self.store.compare_and_set_task(
                task.task_id,
                expected_version=task.state_version,
                expected_status=TaskState.PENDING.value,
                target_status=TaskState.SKIPPED.value,
                metadata_patch={"skip_reason": reason},
                event_name="task.skipped",
                organization_id=task.organization_id,
                graph_id=task.graph_id,
            )
        except TaskGraphConflictError:
            return False
        async with self.store.connection_factory() as connection:
            async with connection.transaction():
                await _recompute_graph_locked(connection, task.graph_id, now)
        return True


def _row_to_task(row: dict[str, Any]) -> TaskSnapshot:
    metadata = _mapping(row.get("metadata_json"))
    parent = row.get("parent_task_id")
    concurrency = row.get("concurrency_limit")
    return TaskSnapshot(
        task_id=UUID(str(row["id"])),
        graph_id=UUID(str(row["task_graph_id"])),
        organization_id=UUID(str(row["organization_id"])),
        project_id=UUID(str(row["project_id"])),
        agent_run_id=UUID(str(row["agent_run_id"])),
        parent_task_id=UUID(str(parent)) if parent is not None else None,
        task_key=str(row["task_key"]),
        recipe_step_id=str(row["recipe_step_id"]),
        step_type=str(row["type"]),
        owner=str(row.get("owner_key") or row.get("owner_agent_key") or "UNKNOWN"),
        status=TaskState(str(row["status"])),
        depends_on=tuple(UUID(str(value)) for value in row.get("depends_on", ())),
        input_bindings={
            str(key): str(value) for key, value in _mapping(row.get("input_json")).items()
        },
        output_schema=str(row.get("output_schema") or "GenericTaskOutput"),
        priority=int(row.get("priority") or 100),
        attempt_count=int(row.get("attempt_count") or 0),
        max_attempts=int(row.get("max_attempts") or 3),
        budget_limit_usd=_decimal_text(row.get("budget_limit_usd")),
        progress_current=int(row.get("progress_current") or 0),
        progress_total=int(row.get("progress_total") or 1),
        dynamic_depth=int(row.get("dynamic_depth") or 0),
        dynamic_child_limit=int(row.get("dynamic_child_limit") or 0),
        concurrency_group=_optional_text(row.get("concurrency_group")),
        concurrency_limit=int(concurrency) if concurrency is not None else None,
        condition=_optional_text(row.get("condition_expression")),
        wait_reason=_optional_text(row.get("wait_reason")),
        external_ref=_optional_text(row.get("external_ref")),
        retry_not_before=row.get("retry_not_before"),
        lease_owner=_optional_text(row.get("lease_owner")),
        lease_expires_at=row.get("lease_expires_at"),
        heartbeat_at=row.get("heartbeat_at"),
        cancellation_requested_at=row.get("cancellation_requested_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("finished_at"),
        state_version=int(row.get("state_version") or 1),
        output=_mapping(row.get("output_json")),
        error=_mapping(metadata.get("last_error")),
        metadata=metadata,
    )


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _decimal_text(value: object) -> str | None:
    return None if value is None else format(Decimal(str(value)), "f")
