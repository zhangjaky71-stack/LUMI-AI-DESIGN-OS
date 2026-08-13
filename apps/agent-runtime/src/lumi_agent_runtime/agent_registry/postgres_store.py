from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from .errors import AgentProvenanceConflictError
from .provenance import AgentProvenance


class AsyncConnectionFactory(Protocol):
    async def __call__(self) -> Any: ...


class PostgresAgentRunProvenanceStore:
    def __init__(self, connection_factory: AsyncConnectionFactory) -> None:
        self.connection_factory = connection_factory

    async def freeze(
        self,
        *,
        agent_run_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        provenance: AgentProvenance,
    ) -> bool:
        connection = await self.connection_factory()
        try:
            await connection.execute(
                """
                INSERT INTO agent_run_provenance (
                    agent_run_id, organization_id, project_id, requested_ref,
                    agent_id, exact_version, release_status, definition_hash,
                    system_prompt_hash, release_manifest_revision, provenance_hash,
                    dependencies_json, created_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,now())
                ON CONFLICT (agent_run_id) DO NOTHING
                """,
                agent_run_id,
                organization_id,
                project_id,
                provenance.requested_ref,
                provenance.agent_id,
                provenance.exact_version,
                provenance.release_status.value,
                provenance.definition_hash,
                provenance.system_prompt_hash,
                provenance.release_manifest_revision,
                provenance.freeze_hash,
                _dependencies_json(provenance),
            )
            row = await connection.fetchrow(
                "SELECT provenance_hash FROM agent_run_provenance WHERE agent_run_id=$1",
                agent_run_id,
            )
            if row is None:
                raise AgentProvenanceConflictError("provenance insert disappeared")
            if row["provenance_hash"] != provenance.freeze_hash:
                raise AgentProvenanceConflictError("AgentRun already frozen with different provenance")
            inserted = await connection.fetchval(
                "SELECT created_at = updated_at FROM agent_runs WHERE id=$1",
                agent_run_id,
            )
            return bool(inserted) if inserted is not None else False
        finally:
            await connection.close()


def _dependencies_json(provenance: AgentProvenance) -> str:
    return json.dumps(
        [
            {
                "kind": item.kind,
                "key": item.key,
                "requested": item.requested,
                "exact_version": item.exact_version,
                "content_hash": item.content_hash,
                "source_ref": item.source_ref,
            }
            for item in provenance.dependencies
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
