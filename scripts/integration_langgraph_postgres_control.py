from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from lumi_agent_runtime.control_plane.contracts import (
    CheckpointPointer,
    GraphDefinition,
    GraphInterrupt,
    GraphRunRequest,
    GraphRunSnapshot,
    GraphRunStatus,
    InterruptKind,
)
from lumi_agent_runtime.control_plane.errors import GraphCheckpointConflictError
from lumi_agent_runtime.control_plane.postgres_store import PostgresGraphRunStore
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


class RuntimeConnectionFactory:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def __call__(self):
        return await asyncpg.connect(self.dsn)


async def _must_deny(connection: asyncpg.Connection, statement: str) -> None:
    try:
        await connection.execute(statement)
    except asyncpg.InsufficientPrivilegeError:
        return
    raise AssertionError(f"runtime mutation must be denied: {statement}")


async def main_async() -> None:
    runtime_dsn = _dsn("DATABASE_URL")
    migration_dsn = _dsn("MIGRATION_DATABASE_URL")
    runtime = await asyncpg.connect(runtime_dsn)
    admin = await asyncpg.connect(migration_dsn)
    store = PostgresGraphRunStore(RuntimeConnectionFactory(runtime_dsn))
    graph_id = uuid4()
    agent_run_id = uuid4()
    try:
        seeded_run = await admin.fetchrow(
            """
            SELECT thread_id, graph_version, agent_config_version
            FROM agent_runs
            WHERE organization_id=$1 AND project_id=$2
            ORDER BY created_at LIMIT 1
            """,
            ORG_ID,
            PROJECT_A_ID,
        )
        assert seeded_run is not None
        # NODE-28 acceptance owns its own AgentRun so thread/version identity is explicit.
        thread_id = f"node28-{uuid4()}"
        await admin.execute(
            """
            INSERT INTO agent_runs (
                id, organization_id, project_id, thread_id, graph_version,
                agent_config_version, status, budget, started_at, version
            ) VALUES ($1,$2,$3,$4,'1.0.0','agent-v1','pending','{}'::jsonb,now(),1)
            """,
            agent_run_id,
            ORG_ID,
            PROJECT_A_ID,
            thread_id,
        )
        definition = GraphDefinition(
            graph_key="acceptance.postgres",
            graph_version="1.0.0",
            agent_config_version="agent-v1",
            description="NODE-28 PostgreSQL control metadata acceptance",
            state_schema_version=1,
        )
        await admin.execute(
            """
            INSERT INTO agent_graph_definitions (
                id, graph_key, graph_version, agent_config_version, description,
                state_schema_version, input_schema_version, output_schema_version,
                interrupt_policy_version, content_hash, enabled, metadata_json,
                created_at, updated_at
            ) VALUES ($1,$2,$3,$4,$5,1,1,1,'1',$6,true,'{}'::jsonb,now(),now())
            """,
            graph_id,
            definition.graph_key,
            definition.graph_version,
            definition.agent_config_version,
            definition.description,
            definition.content_hash,
        )
        request = GraphRunRequest(
            organization_id=ORG_ID,
            project_id=PROJECT_A_ID,
            agent_run_id=agent_run_id,
            operation_id=uuid4(),
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            input={"brief": "postgres acceptance"},
            thread_id=thread_id,
        )
        assert await store.bind_start(request, definition) is None
        now = datetime.now(UTC)
        paused = GraphRunSnapshot(
            organization_id=ORG_ID,
            project_id=PROJECT_A_ID,
            agent_run_id=agent_run_id,
            task_id=None,
            thread_id=thread_id,
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            status=GraphRunStatus.INTERRUPTED,
            checkpoint_id="cp-1",
            checkpoint_namespace="",
            state_values={"draft": "ready"},
            next_nodes=("review",),
            interrupts=(
                GraphInterrupt(
                    interrupt_id="i-1",
                    kind=InterruptKind.APPROVAL,
                    namespace=("review",),
                    node_name="review",
                    payload={"kind": "approval", "approval_id": str(uuid4())},
                    resumable=True,
                ),
            ),
            created_at=now,
            updated_at=now,
        )
        await store.persist_snapshot(paused, expected_checkpoint=None)
        replay = await store.bind_start(request, definition)
        assert replay is not None
        assert replay.checkpoint_id == "cp-1"
        binding = await store.resolve_thread(thread_id)
        assert binding.graph_key == definition.graph_key
        assert binding.graph_version == definition.graph_version

        done = GraphRunSnapshot(
            organization_id=ORG_ID,
            project_id=PROJECT_A_ID,
            agent_run_id=agent_run_id,
            task_id=None,
            thread_id=thread_id,
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            status=GraphRunStatus.SUCCEEDED,
            checkpoint_id="cp-2",
            checkpoint_namespace="",
            state_values={"finished": True},
            next_nodes=(),
            interrupts=(),
            created_at=now,
            updated_at=datetime.now(UTC),
        )
        try:
            await store.persist_snapshot(
                done,
                expected_checkpoint=CheckpointPointer(
                    thread_id=thread_id,
                    checkpoint_namespace="",
                    checkpoint_id="stale",
                ),
            )
        except GraphCheckpointConflictError:
            pass
        else:
            raise AssertionError("stale checkpoint persist must fail")
        await store.persist_snapshot(
            done,
            expected_checkpoint=CheckpointPointer(
                thread_id=thread_id,
                checkpoint_namespace="",
                checkpoint_id="cp-1",
            ),
        )
        current = await store.load(agent_run_id)
        assert current is not None
        assert current.status == GraphRunStatus.SUCCEEDED
        assert current.checkpoint_id == "cp-2"

        # Runtime may read definitions and update run-control metadata, but control-plane
        # definitions are admin-owned and run-control rows cannot be deleted by runtime.
        visible = await runtime.fetchval(
            "SELECT count(*) FROM agent_graph_definitions WHERE graph_key=$1",
            definition.graph_key,
        )
        assert int(visible) == 1
        await _must_deny(
            runtime,
            "UPDATE agent_graph_definitions SET enabled=false WHERE false",
        )
        await _must_deny(runtime, "DELETE FROM agent_graph_definitions WHERE false")
        await _must_deny(runtime, "DELETE FROM agent_run_control WHERE false")
    finally:
        await admin.execute("DELETE FROM agent_run_control WHERE agent_run_id=$1", agent_run_id)
        await admin.execute("DELETE FROM agent_graph_definitions WHERE id=$1", graph_id)
        await admin.execute("DELETE FROM agent_runs WHERE id=$1", agent_run_id)
        await runtime.close()
        await admin.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-28 PostgreSQL graph control metadata integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
