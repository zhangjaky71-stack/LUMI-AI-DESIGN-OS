from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg

from integration_recipe_engine import build_compiler
from lumi_agent_runtime.task_graph import PostgresTaskGraphStore, instantiate_compiled_recipe

ORG_ID = UUID("01900000-0000-7000-8000-000000000001")
PROJECT_ID = UUID("01900000-0000-7000-8000-000000000006")


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def runtime_connection():
    connection = await asyncpg.connect(_dsn("DATABASE_URL"))
    try:
        yield connection
    finally:
        await connection.close()


async def main_async() -> None:
    migration = await asyncpg.connect(_dsn("MIGRATION_DATABASE_URL"))
    runtime = await asyncpg.connect(_dsn("DATABASE_URL"))
    agent_run_id = uuid4()
    graph_id: UUID | None = None
    try:
        assert await migration.fetchval("SELECT count(*) FROM organizations WHERE id = $1", ORG_ID) == 1
        assert await migration.fetchval("SELECT count(*) FROM projects WHERE id = $1", PROJECT_ID) == 1
        await migration.execute(
            """
            INSERT INTO agent_runs (
                id, organization_id, project_id, thread_id, graph_version,
                agent_config_version, status, budget_json
            ) VALUES ($1,$2,$3,$4,'node33-v1','recipe-engine-v1','pending','{}'::jsonb)
            """,
            agent_run_id,
            ORG_ID,
            PROJECT_ID,
            f"node33-postgres-{agent_run_id}",
        )

        compiled = build_compiler().compile("product-visuals@production")
        bundle = instantiate_compiled_recipe(
            compiled,
            organization_id=ORG_ID,
            project_id=PROJECT_ID,
            agent_run_id=agent_run_id,
        )
        graph_id = bundle.graph.graph_id
        store = PostgresTaskGraphStore(runtime_connection)
        await store.install(bundle)
        loaded_graph = await store.load_graph(graph_id)
        assert loaded_graph is not None
        assert str(loaded_graph["provenance_hash"]) == bundle.graph.provenance.freeze_hash
        assert len(await store.list_tasks(graph_id)) == len(bundle.tasks)

        render_ids = tuple(
            task.task_id for task in bundle.tasks if task.concurrency_group == "renders"
        )
        assert len(render_ids) == 3
        # Recipe dependency/join rules are covered by the pure runtime E2E. Isolate the
        # validated render fan-out here so this test specifically exercises DB claiming.
        await migration.execute(
            "UPDATE tasks SET status = 'PENDING' WHERE task_graph_id = $1",
            graph_id,
        )
        await migration.execute(
            "UPDATE tasks SET status = 'READY' WHERE id = ANY($1::uuid[])",
            list(render_ids),
        )

        now = datetime.now(UTC)
        worker_a, worker_b = "node33-db-a", "node33-db-b"
        claimed_a, claimed_b = await asyncio.gather(
            store.claim_ready(graph_id, worker_id=worker_a, now=now, lease_seconds=60, limit=8),
            store.claim_ready(graph_id, worker_id=worker_b, now=now, lease_seconds=60, limit=8),
        )
        all_claims = [(worker_a, row) for row in claimed_a] + [
            (worker_b, row) for row in claimed_b
        ]
        claimed_ids = [UUID(str(row["id"])) for _, row in all_claims]
        assert len(claimed_ids) == 3, claimed_ids
        assert len(set(claimed_ids)) == 3, claimed_ids
        assert set(claimed_ids) == set(render_ids)

        worker, first = all_claims[0]
        task_id = UUID(str(first["id"]))
        failed = await store.finish_running(
            task_id,
            worker_id=worker,
            now=now,
            target_status="FAILED_RETRYABLE",
            error_category="transient",
            error={"code": "NODE33_INTEGRATION_RETRY"},
        )
        await store.schedule_retry(
            task_id,
            expected_version=int(failed["state_version"]),
            retry_not_before=now,
        )
        second_claim = await store.claim_ready(
            graph_id,
            worker_id="node33-db-retry",
            now=now,
            lease_seconds=60,
            limit=1,
        )
        assert len(second_claim) == 1
        assert UUID(str(second_claim[0]["id"])) == task_id

        attempts = await runtime.fetch(
            """
            SELECT attempt_number, logical_operation_key, status
            FROM task_attempts
            WHERE task_id = $1
            ORDER BY attempt_number
            """,
            task_id,
        )
        assert [int(row["attempt_number"]) for row in attempts] == [1, 2]
        expected_key = f"task:{graph_id}:{task_id}"
        assert {str(row["logical_operation_key"]) for row in attempts} == {expected_key}

        timeline = await store.timeline(graph_id)
        assert len(timeline) == len(bundle.tasks)
        assert any(UUID(str(row["task_id"])) == task_id for row in timeline)
        outbox_count = await runtime.fetchval(
            "SELECT count(*) FROM outbox_events WHERE payload_json->>'graph_id' = $1",
            str(graph_id),
        )
        assert int(outbox_count) >= 5

        try:
            await runtime.execute("DELETE FROM task_attempts WHERE task_id = $1", task_id)
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            raise AssertionError("lumi_app must not delete Task attempt history")
    finally:
        if graph_id is not None:
            await migration.execute(
                "DELETE FROM outbox_events WHERE payload_json->>'graph_id' = $1",
                str(graph_id),
            )
        await migration.execute("DELETE FROM agent_runs WHERE id = $1", agent_run_id)
        await runtime.close()
        await migration.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-33 PostgreSQL Task Graph scheduler integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
