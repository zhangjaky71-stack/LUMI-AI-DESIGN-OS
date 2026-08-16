from __future__ import annotations

import json
from importlib import import_module
from typing import Any, Callable
from uuid import UUID

from .contracts import RunControlSnapshot, RunStatus
from .errors import CheckpointUnavailable, ResumeVersionConflict, RunConflict, RunNotFound


class PostgresRunControlStore:
    """Tenant-RLS-aware durable projection beside LangGraph's own checkpoint tables."""

    def __init__(
        self,
        dsn: str,
        *,
        definition_hash: Callable[[str, str], str],
    ) -> None:
        self.dsn = _dsn(dsn)
        self.definition_hash = definition_hash

    async def load(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
    ) -> RunControlSnapshot | None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                row = await connection.fetchrow(
                    "SELECT * FROM agent_run_control WHERE agent_run_id=$1",
                    agent_run_id,
                )
        finally:
            await connection.close()
        return None if row is None else _snapshot(row)

    async def create(self, snapshot: RunControlSnapshot) -> None:
        connection = await self._connect()
        definition_hash = self.definition_hash(snapshot.graph_key, snapshot.graph_version)
        try:
            async with connection.transaction():
                await _set_tenant(connection, snapshot.organization_id)
                await connection.execute(
                    """
                    INSERT INTO agent_run_control (
                      agent_run_id, organization_id, project_id, task_id,
                      graph_key, graph_version, code_git_sha, graph_definition_hash,
                      thread_id, control_status, checkpoint_id, checkpoint_namespace,
                      state_values_json, next_nodes_json, interrupts_json, resume_version,
                      error_code, created_at, updated_at, version
                    ) VALUES (
                      $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                      $13::jsonb,$14::jsonb,$15::jsonb,$16,$17,$18,$19,1
                    )
                    """,
                    snapshot.agent_run_id,
                    snapshot.organization_id,
                    snapshot.project_id,
                    snapshot.task_id,
                    snapshot.graph_key,
                    snapshot.graph_version,
                    snapshot.code_git_sha,
                    definition_hash,
                    snapshot.thread_id,
                    snapshot.status.value,
                    snapshot.checkpoint_id,
                    snapshot.checkpoint_namespace,
                    _json(snapshot.state),
                    _json(list(snapshot.next_nodes)),
                    _json(list(snapshot.interrupts)),
                    snapshot.resume_version,
                    snapshot.error_code,
                    snapshot.created_at,
                    snapshot.updated_at,
                )
                updated = await connection.execute(
                    """
                    UPDATE agent_runs
                    SET thread_id=$2, graph_version=$3, graph_key=$4, code_git_sha=$5,
                        status=$6, updated_at=now(), version=version+1
                    WHERE id=$1 AND organization_id=$7
                    """,
                    snapshot.agent_run_id,
                    snapshot.thread_id,
                    snapshot.graph_version,
                    snapshot.graph_key,
                    snapshot.code_git_sha,
                    _agent_run_status(snapshot.status),
                    snapshot.organization_id,
                )
                if updated != "UPDATE 1":
                    raise RunNotFound(str(snapshot.agent_run_id))
        finally:
            await connection.close()

    async def compare_and_set(
        self,
        snapshot: RunControlSnapshot,
        *,
        expected_checkpoint_id: str | None,
        expected_resume_version: int,
    ) -> None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                await _set_tenant(connection, snapshot.organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE agent_run_control
                    SET control_status=$4, checkpoint_id=$5, checkpoint_namespace=$6,
                        state_values_json=$7::jsonb, next_nodes_json=$8::jsonb,
                        interrupts_json=$9::jsonb, resume_version=$10, error_code=$11,
                        updated_at=$12, version=version+1
                    WHERE agent_run_id=$1 AND organization_id=$2
                      AND checkpoint_id IS NOT DISTINCT FROM $3
                      AND resume_version=$13
                    RETURNING version
                    """,
                    snapshot.agent_run_id,
                    snapshot.organization_id,
                    expected_checkpoint_id,
                    snapshot.status.value,
                    snapshot.checkpoint_id,
                    snapshot.checkpoint_namespace,
                    _json(snapshot.state),
                    _json(list(snapshot.next_nodes)),
                    _json(list(snapshot.interrupts)),
                    snapshot.resume_version,
                    snapshot.error_code,
                    snapshot.updated_at,
                    expected_resume_version,
                )
                if row is None:
                    current = await connection.fetchrow(
                        """
                        SELECT checkpoint_id, resume_version FROM agent_run_control
                        WHERE agent_run_id=$1
                        """,
                        snapshot.agent_run_id,
                    )
                    if current is None:
                        raise RunNotFound(str(snapshot.agent_run_id))
                    if int(current["resume_version"]) != expected_resume_version:
                        raise ResumeVersionConflict("RESUME_VERSION_CAS_MISMATCH")
                    raise RunConflict("CHECKPOINT_CAS_MISMATCH")
                await connection.execute(
                    """
                    UPDATE agent_runs
                    SET status=$2, updated_at=now(), version=version+1
                    WHERE id=$1 AND organization_id=$3
                    """,
                    snapshot.agent_run_id,
                    _agent_run_status(snapshot.status),
                    snapshot.organization_id,
                )
        finally:
            await connection.close()

    async def _connect(self):
        try:
            asyncpg = import_module("asyncpg")
        except ImportError as exc:
            raise CheckpointUnavailable("ASYNC_PG_RUNTIME_DEPENDENCY_MISSING") from exc
        return await asyncpg.connect(self.dsn)


def _snapshot(row: Any) -> RunControlSnapshot:
    return RunControlSnapshot(
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        agent_run_id=row["agent_run_id"],
        task_id=row["task_id"],
        thread_id=row["thread_id"],
        graph_key=row["graph_key"],
        graph_version=row["graph_version"],
        code_git_sha=row["code_git_sha"],
        status=RunStatus(row["control_status"]),
        checkpoint_id=row["checkpoint_id"],
        checkpoint_namespace=row["checkpoint_namespace"],
        state=dict(row["state_values_json"] or {}),
        next_nodes=tuple(row["next_nodes_json"] or ()),
        interrupts=tuple(dict(item) for item in (row["interrupts_json"] or ())),
        resume_version=int(row["resume_version"]),
        error_code=row["error_code"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _set_tenant(connection: Any, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id',$1,true)",
        str(organization_id),
    )


def _agent_run_status(status: RunStatus) -> str:
    return status.value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dsn(value: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if value.startswith(prefix):
            return "postgresql://" + value[len(prefix) :]
    return value
