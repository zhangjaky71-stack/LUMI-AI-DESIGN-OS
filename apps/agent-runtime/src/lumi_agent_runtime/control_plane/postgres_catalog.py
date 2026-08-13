from __future__ import annotations

from typing import Any

from .contracts import GraphDefinition
from .errors import GraphNotFoundError, GraphVersionConflictError
from .postgres_store import AsyncConnectionFactory


class PostgresGraphDefinitionCatalog:
    """Durable provenance catalog; use an admin/migration connection for install()."""

    def __init__(self, connection_factory: AsyncConnectionFactory) -> None:
        self.connection_factory = connection_factory

    async def install(self, definition: GraphDefinition, *, definition_id: Any) -> None:
        connection = await self.connection_factory()
        try:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    """
                    SELECT * FROM agent_graph_definitions
                    WHERE graph_key=$1 AND graph_version=$2
                    FOR UPDATE
                    """,
                    definition.graph_key,
                    definition.graph_version,
                )
                if existing is not None:
                    if (
                        existing["content_hash"] != definition.content_hash
                        or existing["agent_config_version"]
                        != definition.agent_config_version
                        or int(existing["state_schema_version"])
                        != definition.state_schema_version
                        or int(existing["input_schema_version"])
                        != definition.input_schema_version
                        or int(existing["output_schema_version"])
                        != definition.output_schema_version
                        or existing["interrupt_policy_version"]
                        != definition.interrupt_policy_version
                    ):
                        raise GraphVersionConflictError(
                            "immutable graph version already exists with different content"
                        )
                    await connection.execute(
                        """
                        UPDATE agent_graph_definitions
                        SET enabled=$3, updated_at=now()
                        WHERE graph_key=$1 AND graph_version=$2
                        """,
                        definition.graph_key,
                        definition.graph_version,
                        definition.enabled,
                    )
                    return
                await connection.execute(
                    """
                    INSERT INTO agent_graph_definitions (
                        id, graph_key, graph_version, agent_config_version, description,
                        state_schema_version, input_schema_version, output_schema_version,
                        interrupt_policy_version, content_hash, enabled, metadata_json,
                        created_at, updated_at
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,now(),now()
                    )
                    """,
                    definition_id,
                    definition.graph_key,
                    definition.graph_version,
                    definition.agent_config_version,
                    definition.description,
                    definition.state_schema_version,
                    definition.input_schema_version,
                    definition.output_schema_version,
                    definition.interrupt_policy_version,
                    definition.content_hash,
                    definition.enabled,
                    _json(definition.metadata),
                )
        finally:
            await connection.close()

    async def verify(self, definition: GraphDefinition) -> None:
        connection = await self.connection_factory()
        try:
            row = await connection.fetchrow(
                """
                SELECT content_hash, agent_config_version, enabled
                FROM agent_graph_definitions
                WHERE graph_key=$1 AND graph_version=$2
                """,
                definition.graph_key,
                definition.graph_version,
            )
            if row is None:
                raise GraphNotFoundError(
                    f"graph definition not installed: {definition.identity}"
                )
            if (
                row["content_hash"] != definition.content_hash
                or row["agent_config_version"] != definition.agent_config_version
            ):
                raise GraphVersionConflictError(
                    "runtime graph definition differs from durable catalog"
                )
            if not bool(row["enabled"]):
                raise GraphVersionConflictError("durable graph definition is disabled")
        finally:
            await connection.close()


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
