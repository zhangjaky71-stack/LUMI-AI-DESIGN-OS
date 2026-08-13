from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from .contracts import (
    CheckpointPointer,
    GraphDefinition,
    GraphInterrupt,
    GraphRunRequest,
    GraphRunSnapshot,
    GraphRunStatus,
    InterruptKind,
)
from .durable_executor import ThreadGraphBinding
from .errors import (
    GraphCheckpointConflictError,
    GraphRunConflictError,
    GraphRunNotFoundError,
)


class AsyncConnectionFactory(Protocol):
    async def __call__(self) -> Any: ...


class PostgresGraphRunStore:
    """SDK-neutral SQL implementation of GraphRunStore + ThreadGraphBindingResolver.

    The package contains no asyncpg import. Production composition injects a connection
    factory backed by the API/runtime pool. LangGraph checkpoints remain execution truth;
    this table stores LUMI's control metadata and a bounded JSON-compatible snapshot copy
    for idempotent command responses/audit.
    """

    def __init__(self, connection_factory: AsyncConnectionFactory) -> None:
        self.connection_factory = connection_factory

    async def bind_start(
        self,
        request: GraphRunRequest,
        definition: GraphDefinition,
    ) -> GraphRunSnapshot | None:
        connection = await self.connection_factory()
        try:
            async with connection.transaction():
                await _lock_run(connection, request.agent_run_id)
                base = await connection.fetchrow(
                    """
                    SELECT id, organization_id, project_id, thread_id,
                           graph_version, agent_config_version
                    FROM agent_runs WHERE id=$1
                    """,
                    request.agent_run_id,
                )
                if base is None:
                    raise GraphRunNotFoundError(f"AgentRun not found: {request.agent_run_id}")
                if (
                    base["organization_id"] != request.organization_id
                    or base["project_id"] != request.project_id
                    or base["thread_id"] != request.thread_id
                    or base["graph_version"] != request.graph_version
                    or base["agent_config_version"] != request.agent_config_version
                ):
                    raise GraphRunConflictError("AgentRun identity does not match graph start")
                row = await connection.fetchrow(
                    "SELECT * FROM agent_run_control WHERE agent_run_id=$1 FOR UPDATE",
                    request.agent_run_id,
                )
                if row is not None:
                    _assert_binding(row, request, definition)
                    return _snapshot_from_row(row)
                await connection.execute(
                    """
                    INSERT INTO agent_run_control (
                        agent_run_id, organization_id, project_id, task_id,
                        graph_key, graph_version, agent_config_version,
                        graph_definition_hash, thread_id, control_status,
                        checkpoint_namespace, state_values_json, next_nodes_json,
                        interrupts_json, created_at, updated_at, version
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,'pending','',
                        '{}'::jsonb,'[]'::jsonb,'[]'::jsonb,now(),now(),1
                    )
                    """,
                    request.agent_run_id,
                    request.organization_id,
                    request.project_id,
                    request.task_id,
                    definition.graph_key,
                    definition.graph_version,
                    definition.agent_config_version,
                    definition.content_hash,
                    request.thread_id,
                )
                return None
        finally:
            await connection.close()

    async def persist_snapshot(
        self,
        snapshot: GraphRunSnapshot,
        *,
        expected_checkpoint: CheckpointPointer | None,
    ) -> None:
        connection = await self.connection_factory()
        try:
            async with connection.transaction():
                await _lock_run(connection, snapshot.agent_run_id)
                row = await connection.fetchrow(
                    "SELECT * FROM agent_run_control WHERE agent_run_id=$1 FOR UPDATE",
                    snapshot.agent_run_id,
                )
                if row is None:
                    raise GraphRunNotFoundError(
                        f"AgentRun control not found: {snapshot.agent_run_id}"
                    )
                _assert_snapshot_identity(row, snapshot)
                if expected_checkpoint is not None:
                    if (
                        row["thread_id"] != expected_checkpoint.thread_id
                        or row["checkpoint_namespace"]
                        != expected_checkpoint.checkpoint_namespace
                        or row["checkpoint_id"] != expected_checkpoint.checkpoint_id
                    ):
                        raise GraphCheckpointConflictError(
                            "checkpoint advanced before control-plane persist"
                        )
                await connection.execute(
                    """
                    UPDATE agent_run_control
                    SET task_id=$2, control_status=$3, checkpoint_id=$4,
                        checkpoint_namespace=$5, state_values_json=$6::jsonb,
                        next_nodes_json=$7::jsonb, interrupts_json=$8::jsonb,
                        error_code=$9, updated_at=now(), version=version+1
                    WHERE agent_run_id=$1
                    """,
                    snapshot.agent_run_id,
                    snapshot.task_id,
                    snapshot.status.value,
                    snapshot.checkpoint_id,
                    snapshot.checkpoint_namespace,
                    _json(snapshot.state_values),
                    _json(list(snapshot.next_nodes)),
                    _json([_interrupt_json(item) for item in snapshot.interrupts]),
                    snapshot.error_code,
                )
        finally:
            await connection.close()

    async def load(self, agent_run_id: UUID) -> GraphRunSnapshot | None:
        connection = await self.connection_factory()
        try:
            row = await connection.fetchrow(
                "SELECT * FROM agent_run_control WHERE agent_run_id=$1",
                agent_run_id,
            )
            return _snapshot_from_row(row) if row is not None else None
        finally:
            await connection.close()

    async def resolve_thread(self, thread_id: str) -> ThreadGraphBinding:
        connection = await self.connection_factory()
        try:
            row = await connection.fetchrow(
                """
                SELECT thread_id, graph_key, graph_version, agent_config_version, task_id
                FROM agent_run_control WHERE thread_id=$1
                """,
                thread_id,
            )
            if row is None:
                raise GraphRunNotFoundError(f"thread binding not found: {thread_id}")
            return ThreadGraphBinding(
                thread_id=row["thread_id"],
                graph_key=row["graph_key"],
                graph_version=row["graph_version"],
                agent_config_version=row["agent_config_version"],
                task_id=row["task_id"],
            )
        finally:
            await connection.close()


async def _lock_run(connection: Any, agent_run_id: UUID) -> None:
    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
        f"langgraph-run:{agent_run_id}",
    )


def _assert_binding(
    row: Any,
    request: GraphRunRequest,
    definition: GraphDefinition,
) -> None:
    if (
        row["organization_id"] != request.organization_id
        or row["project_id"] != request.project_id
        or row["thread_id"] != request.thread_id
        or row["graph_key"] != definition.graph_key
        or row["graph_version"] != definition.graph_version
        or row["agent_config_version"] != definition.agent_config_version
        or row["graph_definition_hash"] != definition.content_hash
    ):
        raise GraphRunConflictError("graph start replay differs from immutable run binding")


def _assert_snapshot_identity(row: Any, snapshot: GraphRunSnapshot) -> None:
    if (
        row["organization_id"] != snapshot.organization_id
        or row["project_id"] != snapshot.project_id
        or row["thread_id"] != snapshot.thread_id
        or row["graph_key"] != snapshot.graph_key
        or row["graph_version"] != snapshot.graph_version
        or row["agent_config_version"] != snapshot.agent_config_version
    ):
        raise GraphRunConflictError("snapshot identity differs from AgentRun control binding")


def _snapshot_from_row(row: Any) -> GraphRunSnapshot:
    created = _datetime(row["created_at"])
    updated = _datetime(row["updated_at"])
    interrupts_raw = row["interrupts_json"] or []
    interrupts = tuple(_interrupt_from_json(item) for item in interrupts_raw)
    return GraphRunSnapshot(
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        agent_run_id=row["agent_run_id"],
        task_id=row["task_id"],
        thread_id=row["thread_id"],
        graph_key=row["graph_key"],
        graph_version=row["graph_version"],
        agent_config_version=row["agent_config_version"],
        status=GraphRunStatus(row["control_status"]),
        checkpoint_id=row["checkpoint_id"],
        checkpoint_namespace=row["checkpoint_namespace"],
        state_values=dict(row["state_values_json"] or {}),
        next_nodes=tuple(str(item) for item in (row["next_nodes_json"] or [])),
        interrupts=interrupts,
        created_at=created,
        updated_at=updated,
        error_code=row["error_code"],
    )


def _interrupt_json(interrupt: GraphInterrupt) -> dict[str, Any]:
    return {
        "interrupt_id": interrupt.interrupt_id,
        "kind": interrupt.kind.value,
        "namespace": list(interrupt.namespace),
        "node_name": interrupt.node_name,
        "payload": interrupt.payload,
        "resumable": interrupt.resumable,
        "created_at": interrupt.created_at.isoformat(),
    }


def _interrupt_from_json(value: Any) -> GraphInterrupt:
    if not isinstance(value, dict):
        raise GraphRunConflictError("persisted interrupt is not an object")
    return GraphInterrupt(
        interrupt_id=str(value.get("interrupt_id", "")),
        kind=InterruptKind(str(value.get("kind", InterruptKind.REVIEW.value))),
        namespace=tuple(str(item) for item in value.get("namespace", [])),
        node_name=(str(value["node_name"]) if value.get("node_name") is not None else None),
        payload=dict(value.get("payload", {})),
        resumable=bool(value.get("resumable", True)),
        created_at=_datetime(value.get("created_at")),
    )


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
