from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol
from uuid import UUID, uuid4

from .errors import TaskGraphClaimError, TaskGraphConflictError
from .events import TaskGraphEvent
from .instantiator import InstantiatedTaskGraph
from .task_contracts import logical_operation_key


class TaskGraphDbConnection(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[Any]: ...
    async def execute(self, query: str, *args: object) -> str: ...
    async def executemany(
        self,
        query: str,
        args: list[tuple[object, ...]],
    ) -> None: ...
    async def fetch(self, query: str, *args: object) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: object) -> Any | None: ...


ConnectionFactory = Callable[
    [],
    AbstractAsyncContextManager[TaskGraphDbConnection],
]


class PostgresTaskGraphStore:
    """SDK-neutral durable TaskGraph store with transactional outbox writes."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    async def install(self, bundle: InstantiatedTaskGraph) -> None:
        graph = bundle.graph
        async with self.connection_factory() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT provenance_hash FROM task_graph_instances "
                    "WHERE id = $1 FOR UPDATE",
                    graph.graph_id,
                )
                if existing is not None:
                    if str(existing["provenance_hash"]) != graph.provenance.freeze_hash:
                        raise TaskGraphConflictError("TASK_GRAPH_INSTALL_CONFLICT")
                    return
                await connection.execute(
                    """
                    INSERT INTO task_graph_instances (
                        id, organization_id, project_id, agent_run_id,
                        recipe_id, recipe_version, recipe_definition_hash,
                        recipe_provenance_hash, task_graph_template_hash,
                        provenance_hash, status, recipe_budget_limit_usd,
                        task_count, completed_count, succeeded_count,
                        failed_count, cancelled_count, skipped_count,
                        state_version, started_at
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                        0,0,0,0,0,1,$14
                    )
                    """,
                    graph.graph_id,
                    graph.organization_id,
                    graph.project_id,
                    graph.agent_run_id,
                    graph.provenance.recipe_id,
                    graph.provenance.recipe_version,
                    graph.provenance.recipe_definition_hash,
                    graph.provenance.recipe_provenance_hash,
                    graph.provenance.task_graph_template_hash,
                    graph.provenance.freeze_hash,
                    graph.status.value,
                    graph.recipe_budget_limit_usd,
                    graph.task_count,
                    graph.started_at,
                )
                task_rows: list[tuple[object, ...]] = []
                dependency_rows: list[tuple[object, ...]] = []
                for task in bundle.tasks:
                    task_rows.append(
                        (
                            task.task_id,
                            task.organization_id,
                            task.project_id,
                            task.agent_run_id,
                            task.parent_task_id,
                            task.graph_id,
                            task.recipe_step_id,
                            task.task_key,
                            task.step_type,
                            task.status.value,
                            task.priority,
                            task.max_attempts,
                            task.attempt_count,
                            task.owner,
                            task.budget_limit_usd,
                            task.state_version,
                            task.progress_current,
                            task.progress_total,
                            task.dynamic_depth,
                            task.dynamic_child_limit,
                            task.concurrency_group,
                            task.concurrency_limit,
                            json.dumps(task.input_bindings),
                            json.dumps(task.metadata),
                        )
                    )
                    dependency_rows.extend(
                        (task.task_id, dependency)
                        for dependency in task.depends_on
                    )
                await connection.executemany(
                    """
                    INSERT INTO tasks (
                        id, organization_id, project_id, agent_run_id,
                        parent_task_id, task_graph_id, recipe_step_id,
                        task_key, kind, status, priority, max_attempts,
                        attempt_count, owner_agent, budget_limit_usd,
                        state_version, progress_current, progress_total,
                        dynamic_depth, dynamic_child_limit,
                        concurrency_group, concurrency_limit,
                        input_json, metadata_json
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                        $13,$14,$15,$16,$17,$18,$19,$20,$21,$22,
                        $23::jsonb,$24::jsonb
                    )
                    """,
                    task_rows,
                )
                if dependency_rows:
                    await connection.executemany(
                        """
                        INSERT INTO task_dependencies (
                            task_id, depends_on_task_id
                        ) VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                        """,
                        dependency_rows,
                    )
                for task in bundle.tasks:
                    if task.status.value == "READY":
                        await _insert_outbox(
                            connection,
                            TaskGraphEvent(
                                event_name="task.ready",
                                graph_id=graph.graph_id,
                                task_id=task.task_id,
                                organization_id=task.organization_id,
                                payload={"task_key": task.task_key},
                            ),
                        )

    async def claim_ready(
        self,
        graph_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 60,
        limit: int = 1,
    ) -> tuple[dict[str, Any], ...]:
        if not worker_id or not 5 <= lease_seconds <= 3600 or not 1 <= limit <= 32:
            raise TaskGraphClaimError("TASK_CLAIM_ARGUMENT_INVALID")
        claimed: list[dict[str, Any]] = []
        async with self.connection_factory() as connection:
            async with connection.transaction():
                for _ in range(limit):
                    row = await connection.fetchrow(
                        """
                        SELECT t.*
                        FROM tasks t
                        WHERE t.task_graph_id = $1
                          AND t.status = 'READY'
                          AND t.cancellation_requested_at IS NULL
                          AND (t.retry_not_before IS NULL OR t.retry_not_before <= $2)
                          AND t.attempt_count < t.max_attempts
                          AND (
                            t.concurrency_group IS NULL
                            OR t.concurrency_limit IS NULL
                            OR (
                                SELECT count(*)
                                FROM tasks active
                                WHERE active.task_graph_id = t.task_graph_id
                                  AND active.concurrency_group = t.concurrency_group
                                  AND active.status = 'RUNNING'
                            ) < t.concurrency_limit
                          )
                        ORDER BY t.priority DESC, t.task_key ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                        """,
                        graph_id,
                        now,
                    )
                    if row is None:
                        break
                    task_id = UUID(str(row["id"]))
                    attempt = int(row["attempt_count"]) + 1
                    state_version = int(row["state_version"])
                    updated = await connection.fetchrow(
                        """
                        UPDATE tasks
                        SET status = 'RUNNING',
                            attempt_count = $2,
                            lease_owner = $3,
                            lease_expires_at = $4,
                            heartbeat_at = $5,
                            started_at = COALESCE(started_at, $5),
                            retry_not_before = NULL,
                            wait_reason = NULL,
                            state_version = state_version + 1,
                            updated_at = now()
                        WHERE id = $1
                          AND state_version = $6
                          AND status = 'READY'
                        RETURNING *
                        """,
                        task_id,
                        attempt,
                        worker_id,
                        now + timedelta(seconds=lease_seconds),
                        now,
                        state_version,
                    )
                    if updated is None:
                        continue
                    logical_key = logical_operation_key(graph_id, task_id)
                    await connection.execute(
                        """
                        INSERT INTO task_attempts (
                            id, organization_id, task_graph_id, task_id,
                            attempt_number, logical_operation_key,
                            status, started_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,'RUNNING',$7)
                        """,
                        uuid4(),
                        UUID(str(row["organization_id"])),
                        graph_id,
                        task_id,
                        attempt,
                        logical_key,
                        now,
                    )
                    await _insert_outbox(
                        connection,
                        TaskGraphEvent(
                            event_name="task.started",
                            graph_id=graph_id,
                            task_id=task_id,
                            organization_id=UUID(str(row["organization_id"])),
                            payload={
                                "task_key": str(row["task_key"]),
                                "attempt": attempt,
                                "logical_operation_key": logical_key,
                            },
                        ),
                    )
                    claimed.append(dict(updated))
        return tuple(claimed)

    async def compare_and_set_task(
        self,
        task_id: UUID,
        *,
        expected_version: int,
        expected_status: str,
        target_status: str,
        metadata_patch: dict[str, Any],
        event_name: str,
        organization_id: UUID,
        graph_id: UUID,
    ) -> dict[str, Any]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE tasks
                    SET status = $4,
                        metadata_json = metadata_json || $5::jsonb,
                        state_version = state_version + 1,
                        updated_at = now()
                    WHERE id = $1
                      AND state_version = $2
                      AND status = $3
                    RETURNING *
                    """,
                    task_id,
                    expected_version,
                    expected_status,
                    target_status,
                    json.dumps(metadata_patch),
                )
                if row is None:
                    raise TaskGraphConflictError("TASK_STATE_CAS_CONFLICT")
                await _insert_outbox(
                    connection,
                    TaskGraphEvent(
                        event_name=event_name,
                        graph_id=graph_id,
                        task_id=task_id,
                        organization_id=organization_id,
                        payload={"target_status": target_status},
                    ),
                )
                return dict(row)


async def _insert_outbox(
    connection: TaskGraphDbConnection,
    event: TaskGraphEvent,
) -> None:
    await connection.execute(
        """
        INSERT INTO outbox_events (
            id, organization_id, aggregate_type, aggregate_id,
            event_type, payload, occurred_at, publish_attempts
        ) VALUES ($1,$2,'task_graph',$3,$4,$5::jsonb,now(),0)
        """,
        uuid4(),
        event.organization_id,
        event.task_id or event.graph_id,
        event.event_name,
        json.dumps(event.payload),
    )
