from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Protocol
from uuid import UUID, uuid4, uuid5

from .errors import (
    TaskGraphBudgetError,
    TaskGraphClaimError,
    TaskGraphConflictError,
    TaskGraphExpansionError,
    TaskGraphLeaseError,
    TaskGraphStateError,
)
from .events import TaskGraphEvent
from .instantiator import InstantiatedTaskGraph
from .task_contracts import TaskSnapshot, logical_operation_key


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


ConnectionFactory = Callable[[], AbstractAsyncContextManager[TaskGraphDbConnection]]
_TERMINAL = frozenset({"SUCCEEDED", "FAILED_FINAL", "CANCELLED", "SKIPPED"})
_WAITING = frozenset({"WAITING_APPROVAL", "WAITING_INPUT", "WAITING_EXTERNAL"})
_FINISH_TARGETS = _TERMINAL | _WAITING | {"FAILED_RETRYABLE"}


class PostgresTaskGraphStore:
    """Durable SDK-neutral TaskGraph persistence and scheduling primitives."""

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
                    _decimal_or_none(graph.recipe_budget_limit_usd),
                    graph.task_count,
                    graph.started_at,
                )
                task_rows = [_task_insert_row(task) for task in bundle.tasks]
                await connection.executemany(_TASK_INSERT_SQL, task_rows)
                dependency_rows = [
                    (uuid4(), task.organization_id, task.task_id, dependency)
                    for task in bundle.tasks
                    for dependency in task.depends_on
                ]
                if dependency_rows:
                    await connection.executemany(
                        """
                        INSERT INTO task_dependencies (
                            id, organization_id, task_id, depends_on_task_id
                        ) VALUES ($1,$2,$3,$4)
                        ON CONFLICT (task_id, depends_on_task_id) DO NOTHING
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

    async def load_graph(self, graph_id: UUID) -> dict[str, Any] | None:
        async with self.connection_factory() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM task_graph_instances WHERE id = $1",
                graph_id,
            )
        return dict(row) if row is not None else None

    async def list_tasks(self, graph_id: UUID) -> tuple[dict[str, Any], ...]:
        async with self.connection_factory() as connection:
            rows = await connection.fetch(
                """
                SELECT t.*,
                       COALESCE(
                           array_agg(td.depends_on_task_id)
                           FILTER (WHERE td.depends_on_task_id IS NOT NULL),
                           ARRAY[]::uuid[]
                       ) AS depends_on
                FROM tasks t
                LEFT JOIN task_dependencies td ON td.task_id = t.id
                WHERE t.task_graph_id = $1
                GROUP BY t.id
                ORDER BY t.priority DESC, t.task_key ASC
                """,
                graph_id,
            )
        return tuple(dict(row) for row in rows)

    async def list_attempts(self, graph_id: UUID) -> tuple[dict[str, Any], ...]:
        async with self.connection_factory() as connection:
            rows = await connection.fetch(
                """
                SELECT * FROM task_attempts
                WHERE task_graph_id = $1
                ORDER BY task_id, attempt_number
                """,
                graph_id,
            )
        return tuple(dict(row) for row in rows)

    async def timeline(self, graph_id: UUID) -> tuple[dict[str, Any], ...]:
        async with self.connection_factory() as connection:
            rows = await connection.fetch(
                """
                SELECT t.id AS task_id, t.task_key, t.recipe_step_id, t.type,
                       t.owner_key, t.status, t.priority, t.progress_current,
                       t.progress_total, t.attempt_count, t.started_at,
                       t.finished_at, t.wait_reason, t.external_ref,
                       count(a.id) AS persisted_attempts,
                       max(a.completed_at) AS last_attempt_completed_at
                FROM tasks t
                LEFT JOIN task_attempts a ON a.task_id = t.id
                WHERE t.task_graph_id = $1
                GROUP BY t.id
                ORDER BY t.created_at, t.task_key
                """,
                graph_id,
            )
        return tuple(dict(row) for row in rows)

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
                          AND EXISTS (
                              SELECT 1 FROM task_graph_instances g
                              WHERE g.id = t.task_graph_id
                                AND g.status = 'RUNNING'
                                AND g.cancellation_requested_at IS NULL
                          )
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
                        SET status = 'RUNNING', attempt_count = $2,
                            lease_owner = $3, lease_expires_at = $4,
                            heartbeat_at = $5, started_at = COALESCE(started_at, $5),
                            retry_not_before = NULL, wait_reason = NULL,
                            state_version = state_version + 1, updated_at = now()
                        WHERE id = $1 AND state_version = $6 AND status = 'READY'
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
                            attempt_number, logical_operation_key, status, started_at
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

    async def heartbeat(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 60,
    ) -> dict[str, Any]:
        if not 5 <= lease_seconds <= 3600:
            raise TaskGraphClaimError("TASK_HEARTBEAT_ARGUMENT_INVALID")
        async with self.connection_factory() as connection:
            row = await connection.fetchrow(
                """
                UPDATE tasks
                SET heartbeat_at = $3, lease_expires_at = $4, updated_at = now()
                WHERE id = $1 AND status = 'RUNNING'
                  AND lease_owner = $2 AND lease_expires_at >= $3
                RETURNING *
                """,
                task_id,
                worker_id,
                now,
                now + timedelta(seconds=lease_seconds),
            )
        if row is None:
            raise TaskGraphLeaseError("TASK_HEARTBEAT_LEASE_INVALID")
        return dict(row)

    async def mark_ready(
        self,
        task_id: UUID,
        *,
        expected_version: int,
        expected_status: str = "PENDING",
        event_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE tasks
                    SET status = 'READY', state_version = state_version + 1,
                        updated_at = now()
                    WHERE id = $1 AND state_version = $2 AND status = $3
                      AND cancellation_requested_at IS NULL
                    RETURNING *
                    """,
                    task_id,
                    expected_version,
                    expected_status,
                )
                if row is None:
                    raise TaskGraphConflictError("TASK_READY_CAS_CONFLICT")
                graph_id = UUID(str(row["task_graph_id"]))
                await _set_graph_running(connection, graph_id)
                await _insert_outbox(
                    connection,
                    TaskGraphEvent(
                        event_name="task.ready",
                        graph_id=graph_id,
                        task_id=task_id,
                        organization_id=UUID(str(row["organization_id"])),
                        payload=event_payload or {"task_key": str(row["task_key"])},
                    ),
                )
                return dict(row)

    async def finish_running(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        target_status: str,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        error_category: str | None = None,
        result_ref: str | None = None,
        cost_amount_usd: str | None = None,
        wait_reason: str | None = None,
        external_ref: str | None = None,
    ) -> dict[str, Any]:
        if target_status not in _FINISH_TARGETS:
            raise TaskGraphStateError("TASK_FINISH_TARGET_INVALID")
        async with self.connection_factory() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "SELECT * FROM tasks WHERE id = $1 FOR UPDATE",
                    task_id,
                )
                if current is None:
                    raise TaskGraphConflictError("TASK_NOT_FOUND")
                if (
                    str(current["status"]) != "RUNNING"
                    or str(current["lease_owner"] or "") != worker_id
                    or current["lease_expires_at"] is None
                    or current["lease_expires_at"] < now
                ):
                    raise TaskGraphLeaseError("TASK_FINISH_LEASE_INVALID")
                metadata_patch = {"last_error": dict(error)} if error else {}
                is_terminal = target_status in _TERMINAL
                row = await connection.fetchrow(
                    """
                    UPDATE tasks
                    SET status = $2, output_json = $3::jsonb,
                        metadata_json = metadata_json || $4::jsonb,
                        wait_reason = $5, external_ref = $6,
                        lease_owner = NULL, lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        finished_at = CASE WHEN $7 THEN $8 ELSE finished_at END,
                        state_version = state_version + 1, updated_at = now()
                    WHERE id = $1
                    RETURNING *
                    """,
                    task_id,
                    target_status,
                    json.dumps(output or {}),
                    json.dumps(metadata_patch),
                    wait_reason,
                    external_ref,
                    is_terminal,
                    now,
                )
                attempt = int(current["attempt_count"])
                result = await connection.execute(
                    """
                    UPDATE task_attempts
                    SET status = $3, error_category = $4, result_ref = $5,
                        cost_amount_usd = $6, completed_at = $7
                    WHERE task_id = $1 AND attempt_number = $2
                      AND status = 'RUNNING'
                    """,
                    task_id,
                    attempt,
                    target_status,
                    error_category,
                    result_ref,
                    _decimal_or_none(cost_amount_usd),
                    now,
                )
                if not result.endswith(" 1"):
                    raise TaskGraphConflictError("TASK_ATTEMPT_FINISH_CONFLICT")
                graph_id = UUID(str(current["task_graph_id"]))
                await _insert_outbox(
                    connection,
                    TaskGraphEvent(
                        event_name=_event_for_status(target_status),
                        graph_id=graph_id,
                        task_id=task_id,
                        organization_id=UUID(str(current["organization_id"])),
                        payload={
                            "task_key": str(current["task_key"]),
                            "status": target_status,
                            "attempt": attempt,
                            "error_category": error_category,
                        },
                    ),
                )
                await _recompute_graph_locked(connection, graph_id, now)
                return dict(row)

    async def resume_waiting(
        self,
        task_id: UUID,
        *,
        expected_version: int,
        resume_ref: str,
    ) -> dict[str, Any]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE tasks
                    SET status = 'READY', external_ref = $3, wait_reason = NULL,
                        state_version = state_version + 1, updated_at = now()
                    WHERE id = $1 AND state_version = $2
                      AND status IN ('WAITING_APPROVAL','WAITING_INPUT','WAITING_EXTERNAL')
                      AND cancellation_requested_at IS NULL
                    RETURNING *
                    """,
                    task_id,
                    expected_version,
                    resume_ref,
                )
                if row is None:
                    raise TaskGraphConflictError("TASK_RESUME_CAS_CONFLICT")
                graph_id = UUID(str(row["task_graph_id"]))
                await _set_graph_running(connection, graph_id)
                await _insert_outbox(
                    connection,
                    TaskGraphEvent(
                        event_name="task.ready",
                        graph_id=graph_id,
                        task_id=task_id,
                        organization_id=UUID(str(row["organization_id"])),
                        payload={"resume_ref": resume_ref},
                    ),
                )
                return dict(row)

    async def schedule_retry(
        self,
        task_id: UUID,
        *,
        expected_version: int,
        retry_not_before: datetime,
    ) -> dict[str, Any]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE tasks
                    SET status = 'READY', retry_not_before = $3,
                        state_version = state_version + 1, updated_at = now()
                    WHERE id = $1 AND state_version = $2
                      AND status = 'FAILED_RETRYABLE'
                      AND attempt_count < max_attempts
                      AND cancellation_requested_at IS NULL
                    RETURNING *
                    """,
                    task_id,
                    expected_version,
                    retry_not_before,
                )
                if row is None:
                    raise TaskGraphConflictError("TASK_RETRY_CAS_CONFLICT")
                graph_id = UUID(str(row["task_graph_id"]))
                await _set_graph_running(connection, graph_id)
                await _insert_outbox(
                    connection,
                    TaskGraphEvent(
                        event_name="task.retry_scheduled",
                        graph_id=graph_id,
                        task_id=task_id,
                        organization_id=UUID(str(row["organization_id"])),
                        payload={"retry_not_before": retry_not_before.isoformat()},
                    ),
                )
                return dict(row)

    async def reclaim_expired(
        self,
        graph_id: UUID,
        *,
        now: datetime,
        limit: int = 32,
    ) -> tuple[UUID, ...]:
        if not 1 <= limit <= 256:
            raise TaskGraphClaimError("TASK_RECLAIM_LIMIT_INVALID")
        reclaimed: list[UUID] = []
        async with self.connection_factory() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT * FROM tasks
                    WHERE task_graph_id = $1 AND status = 'RUNNING'
                      AND lease_expires_at < $2
                    ORDER BY lease_expires_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT $3
                    """,
                    graph_id,
                    now,
                    limit,
                )
                for row in rows:
                    task_id = UUID(str(row["id"]))
                    attempt = int(row["attempt_count"])
                    target = (
                        "FAILED_FINAL"
                        if attempt >= int(row["max_attempts"])
                        else "FAILED_RETRYABLE"
                    )
                    await connection.execute(
                        """
                        UPDATE tasks
                        SET status = $2,
                            metadata_json = metadata_json ||
                              '{"provider_reconciliation_required":true,"failure":"lease_expired"}'::jsonb,
                            lease_owner = NULL, lease_expires_at = NULL,
                            heartbeat_at = NULL,
                            finished_at = CASE WHEN $2 = 'FAILED_FINAL' THEN $3 ELSE finished_at END,
                            state_version = state_version + 1, updated_at = now()
                        WHERE id = $1
                        """,
                        task_id,
                        target,
                        now,
                    )
                    result = await connection.execute(
                        """
                        UPDATE task_attempts
                        SET status = $3, error_category = 'lease_expired', completed_at = $4
                        WHERE task_id = $1 AND attempt_number = $2
                          AND status = 'RUNNING'
                        """,
                        task_id,
                        attempt,
                        target,
                        now,
                    )
                    if not result.endswith(" 1"):
                        raise TaskGraphConflictError("TASK_ATTEMPT_RECLAIM_CONFLICT")
                    await _insert_outbox(
                        connection,
                        TaskGraphEvent(
                            event_name="task.failed",
                            graph_id=graph_id,
                            task_id=task_id,
                            organization_id=UUID(str(row["organization_id"])),
                            payload={
                                "status": target,
                                "error_category": "lease_expired",
                                "provider_reconciliation_required": True,
                            },
                        ),
                    )
                    reclaimed.append(task_id)
                if reclaimed:
                    await _recompute_graph_locked(connection, graph_id, now)
        return tuple(reclaimed)

    async def add_dynamic_task(
        self,
        parent_task_id: UUID,
        *,
        child_key: str,
        owner: str,
        step_type: str,
        output_schema: str,
        budget_limit_usd: str | None = None,
        concurrency_group: str | None = None,
        concurrency_limit: int | None = None,
        dynamic_child_limit: int = 0,
    ) -> dict[str, Any]:
        if not child_key or not 0 <= dynamic_child_limit <= 32:
            raise TaskGraphExpansionError("TASK_DYNAMIC_CHILD_ARGUMENT_INVALID")
        async with self.connection_factory() as connection:
            async with connection.transaction():
                parent = await connection.fetchrow(
                    "SELECT * FROM tasks WHERE id = $1 FOR UPDATE",
                    parent_task_id,
                )
                if parent is None or str(parent["status"]) != "RUNNING":
                    raise TaskGraphExpansionError("TASK_DYNAMIC_PARENT_MUST_BE_RUNNING")
                parent_limit = int(parent["dynamic_child_limit"])
                parent_depth = int(parent["dynamic_depth"])
                if parent_limit < 1:
                    raise TaskGraphExpansionError("TASK_DYNAMIC_EXPANSION_NOT_ALLOWED")
                if parent_depth >= 4:
                    raise TaskGraphExpansionError("TASK_DYNAMIC_DEPTH_LIMIT")
                count = await connection.fetchrow(
                    "SELECT count(*) AS count FROM tasks WHERE parent_task_id = $1",
                    parent_task_id,
                )
                if count is None or int(count["count"]) >= parent_limit:
                    raise TaskGraphExpansionError("TASK_DYNAMIC_CHILD_LIMIT")
                parent_budget = parent["budget_limit_usd"]
                if budget_limit_usd is not None and parent_budget is not None:
                    if Decimal(budget_limit_usd) > Decimal(str(parent_budget)):
                        raise TaskGraphBudgetError("TASK_DYNAMIC_BUDGET_ESCALATION")
                parent_concurrency = parent["concurrency_limit"]
                if (
                    concurrency_limit is not None
                    and parent_concurrency is not None
                    and concurrency_limit > int(parent_concurrency)
                ):
                    raise TaskGraphExpansionError("TASK_DYNAMIC_CONCURRENCY_ESCALATION")
                if dynamic_child_limit > parent_limit:
                    raise TaskGraphExpansionError("TASK_DYNAMIC_CHILD_SCOPE_ESCALATION")
                graph_id = UUID(str(parent["task_graph_id"]))
                organization_id = UUID(str(parent["organization_id"]))
                task_id = uuid5(graph_id, f"dynamic:{parent_task_id}:{child_key}")
                metadata = json.dumps({"dynamic": True})
                row = await connection.fetchrow(
                    """
                    INSERT INTO tasks (
                        id, organization_id, project_id, agent_run_id, parent_task_id,
                        task_graph_id, recipe_step_id, task_key, type, status,
                        owner_agent_key, owner_key, input_json, output_json, priority,
                        attempt_count, max_attempts, budget_reserved, budget_limit_usd,
                        output_schema, condition_expression, metadata_json, state_version,
                        progress_current, progress_total, dynamic_depth,
                        dynamic_child_limit, concurrency_group, concurrency_limit
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,'READY',$10,$11,
                        '{}'::jsonb,'{}'::jsonb,$12,0,$13,0,$14,$15,NULL,$16::jsonb,
                        1,0,1,$17,$18,$19,$20
                    )
                    RETURNING *
                    """,
                    task_id,
                    organization_id,
                    UUID(str(parent["project_id"])),
                    UUID(str(parent["agent_run_id"])),
                    parent_task_id,
                    graph_id,
                    str(parent["recipe_step_id"]),
                    f"{parent['task_key']}.{child_key}",
                    step_type,
                    _agent_owner_key(owner),
                    owner,
                    int(parent["priority"]),
                    int(parent["max_attempts"]),
                    _decimal_or_none(budget_limit_usd),
                    output_schema,
                    metadata,
                    parent_depth + 1,
                    dynamic_child_limit,
                    concurrency_group or parent["concurrency_group"],
                    concurrency_limit or parent_concurrency,
                )
                await connection.execute(
                    """
                    UPDATE task_graph_instances
                    SET task_count = task_count + 1, status = 'RUNNING',
                        state_version = state_version + 1, updated_at = now()
                    WHERE id = $1
                    """,
                    graph_id,
                )
                await _insert_outbox(
                    connection,
                    TaskGraphEvent(
                        event_name="task.dynamic_created",
                        graph_id=graph_id,
                        task_id=task_id,
                        organization_id=organization_id,
                        payload={
                            "task_key": str(row["task_key"]),
                            "parent_task_id": str(parent_task_id),
                            "dynamic_depth": parent_depth + 1,
                        },
                    ),
                )
                return dict(row)

    async def request_cancel(self, graph_id: UUID, *, now: datetime) -> dict[str, Any]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                graph = await connection.fetchrow(
                    """
                    UPDATE task_graph_instances
                    SET cancellation_requested_at = COALESCE(cancellation_requested_at, $2),
                        state_version = state_version + 1, updated_at = now()
                    WHERE id = $1
                    RETURNING *
                    """,
                    graph_id,
                    now,
                )
                if graph is None:
                    raise TaskGraphConflictError("TASK_GRAPH_NOT_FOUND")
                await connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'CANCELLED', cancellation_requested_at = $2,
                        finished_at = $2, state_version = state_version + 1,
                        updated_at = now()
                    WHERE task_graph_id = $1
                      AND status IN ('PENDING','READY','FAILED_RETRYABLE',
                                     'WAITING_APPROVAL','WAITING_INPUT','WAITING_EXTERNAL')
                    """,
                    graph_id,
                    now,
                )
                await connection.execute(
                    """
                    UPDATE tasks
                    SET cancellation_requested_at = $2,
                        state_version = state_version + 1, updated_at = now()
                    WHERE task_graph_id = $1 AND status = 'RUNNING'
                    """,
                    graph_id,
                    now,
                )
                await _recompute_graph_locked(connection, graph_id, now)
                return dict(graph)

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
                    SET status = $4, metadata_json = metadata_json || $5::jsonb,
                        state_version = state_version + 1, updated_at = now()
                    WHERE id = $1 AND state_version = $2 AND status = $3
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


_TASK_INSERT_SQL = """
INSERT INTO tasks (
    id, organization_id, project_id, agent_run_id, parent_task_id,
    task_graph_id, recipe_step_id, task_key, type, status,
    owner_agent_key, owner_key, input_json, output_json, priority,
    attempt_count, max_attempts, budget_reserved, budget_limit_usd,
    output_schema, condition_expression, metadata_json, state_version,
    progress_current, progress_total, dynamic_depth, dynamic_child_limit,
    concurrency_group, concurrency_limit
) VALUES (
    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14::jsonb,
    $15,$16,$17,$18,$19,$20,$21,$22::jsonb,$23,$24,$25,$26,$27,$28,$29
)
"""


def _task_insert_row(task: TaskSnapshot) -> tuple[object, ...]:
    return (
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
        _agent_owner_key(task.owner),
        task.owner,
        json.dumps(task.input_bindings),
        json.dumps({}),
        task.priority,
        task.attempt_count,
        task.max_attempts,
        Decimal("0"),
        _decimal_or_none(task.budget_limit_usd),
        task.output_schema,
        task.condition,
        json.dumps(task.metadata),
        task.state_version,
        task.progress_current,
        task.progress_total,
        task.dynamic_depth,
        task.dynamic_child_limit,
        task.concurrency_group,
        task.concurrency_limit,
    )


async def _set_graph_running(connection: TaskGraphDbConnection, graph_id: UUID) -> None:
    await connection.execute(
        """
        UPDATE task_graph_instances
        SET status = 'RUNNING', completed_at = NULL,
            state_version = state_version + 1, updated_at = now()
        WHERE id = $1 AND status = 'WAITING'
        """,
        graph_id,
    )


async def _recompute_graph_locked(
    connection: TaskGraphDbConnection,
    graph_id: UUID,
    now: datetime,
) -> None:
    counts = await connection.fetchrow(
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE status IN ('SUCCEEDED','FAILED_FINAL','CANCELLED','SKIPPED')) AS completed,
               count(*) FILTER (WHERE status = 'SUCCEEDED') AS succeeded,
               count(*) FILTER (WHERE status = 'FAILED_FINAL') AS failed,
               count(*) FILTER (WHERE status = 'CANCELLED') AS cancelled,
               count(*) FILTER (WHERE status = 'SKIPPED') AS skipped,
               count(*) FILTER (WHERE status = 'RUNNING') AS running,
               count(*) FILTER (WHERE status = 'READY') AS ready,
               count(*) FILTER (WHERE status IN ('WAITING_APPROVAL','WAITING_INPUT','WAITING_EXTERNAL')) AS waiting
        FROM tasks WHERE task_graph_id = $1
        """,
        graph_id,
    )
    if counts is None:
        return
    total = int(counts["total"])
    completed = int(counts["completed"])
    failed = int(counts["failed"])
    cancelled = int(counts["cancelled"])
    if total > 0 and completed == total:
        status = "FAILED_FINAL" if failed else ("CANCELLED" if cancelled else "SUCCEEDED")
        completed_at = now
    elif int(counts["waiting"]) and not int(counts["running"]) and not int(counts["ready"]):
        status = "WAITING"
        completed_at = None
    else:
        status = "RUNNING"
        completed_at = None
    await connection.execute(
        """
        UPDATE task_graph_instances
        SET status = $2, completed_count = $3, succeeded_count = $4,
            failed_count = $5, cancelled_count = $6, skipped_count = $7,
            completed_at = $8, state_version = state_version + 1,
            updated_at = now()
        WHERE id = $1
        """,
        graph_id,
        status,
        completed,
        int(counts["succeeded"]),
        failed,
        cancelled,
        int(counts["skipped"]),
        completed_at,
    )


async def _insert_outbox(connection: TaskGraphDbConnection, event: TaskGraphEvent) -> None:
    payload = {
        "graph_id": str(event.graph_id),
        "task_id": str(event.task_id) if event.task_id is not None else None,
        **event.payload,
    }
    await connection.execute(
        """
        INSERT INTO outbox_events (
            id, organization_id, event_name, aggregate_type,
            aggregate_id, schema_version, payload_json, publish_attempts
        ) VALUES ($1,$2,$3,'task_graph',$4,1,$5::jsonb,0)
        """,
        uuid4(),
        event.organization_id,
        event.event_name,
        event.task_id or event.graph_id,
        json.dumps(payload),
    )


def _agent_owner_key(owner: str) -> str | None:
    if not owner.startswith("AGENT:"):
        return None
    value = owner.removeprefix("AGENT:")
    return value.split("@", 1)[0] or None


def _decimal_or_none(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _event_for_status(status: str) -> str:
    if status == "SUCCEEDED":
        return "task.succeeded"
    if status in {"FAILED_RETRYABLE", "FAILED_FINAL"}:
        return "task.failed"
    if status == "CANCELLED":
        return "task.cancelled"
    if status in _WAITING:
        return "task.waiting"
    if status == "SKIPPED":
        return "task.skipped"
    return "task.updated"
