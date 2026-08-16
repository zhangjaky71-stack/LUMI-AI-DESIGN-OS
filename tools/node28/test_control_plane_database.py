from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from lumi_agent_runtime.control_plane.contracts import RunControlSnapshot, RunStatus
from lumi_agent_runtime.control_plane.errors import ResumeVersionConflict
from lumi_agent_runtime.control_plane.postgres_store import PostgresRunControlStore

ORG_A = UUID("00000000-0000-7000-8000-000000002801")
ORG_B = UUID("00000000-0000-7000-8000-000000002802")
WORKSPACE_A = UUID("00000000-0000-7000-8000-000000002811")
PROJECT_A = UUID("00000000-0000-7000-8000-000000002821")
RUN_A = UUID("00000000-0000-7000-8000-000000002831")
GRAPH_DEF = UUID("00000000-0000-7000-8000-000000002841")
GRAPH_HASH = "a" * 64


async def _seed(dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            for org_id, slug in ((ORG_A, "node28-a"), (ORG_B, "node28-b")):
                await connection.execute(
                    """
                    INSERT INTO organizations (id, name, slug)
                    VALUES ($1,$2,$3) ON CONFLICT (id) DO NOTHING
                    """,
                    org_id,
                    slug,
                    slug,
                )
            await connection.execute(
                """
                INSERT INTO workspaces (id, organization_id, name)
                VALUES ($1,$2,'NODE-28 Workspace') ON CONFLICT (id) DO NOTHING
                """,
                WORKSPACE_A,
                ORG_A,
            )
            await connection.execute(
                """
                INSERT INTO projects (id, organization_id, workspace_id, name)
                VALUES ($1,$2,$3,'NODE-28 Project') ON CONFLICT (id) DO NOTHING
                """,
                PROJECT_A,
                ORG_A,
                WORKSPACE_A,
            )
            await connection.execute(
                """
                INSERT INTO agent_runs (
                  id, organization_id, project_id, thread_id, graph_key,
                  graph_version, agent_config_version, code_git_sha, status,
                  budget_amount, budget_currency
                ) VALUES (
                  $1,$2,$3,$4,'lumi.main','1.0.0','1','node28-db-fixture',
                  'pending',10,'USD'
                ) ON CONFLICT (id) DO NOTHING
                """,
                RUN_A,
                ORG_A,
                PROJECT_A,
                str(RUN_A),
            )
            await connection.execute(
                """
                INSERT INTO agent_graph_definitions (
                  id, graph_key, graph_version, agent_config_version, code_git_sha,
                  description, state_schema_version, content_hash, enabled
                ) VALUES (
                  $1,'lumi.main','1.0.0','1','node28-db-fixture',
                  'NODE-28 database fixture',1,$2,true
                ) ON CONFLICT (graph_key, graph_version) DO NOTHING
                """,
                GRAPH_DEF,
                GRAPH_HASH,
            )
    finally:
        await connection.close()


async def _exercise_store(app_dsn: str, migration_dsn: str) -> None:
    store = PostgresRunControlStore(
        app_dsn,
        definition_hash=lambda graph_key, graph_version: GRAPH_HASH,
    )
    now = datetime.now(UTC)
    snapshot = RunControlSnapshot(
        organization_id=ORG_A,
        project_id=PROJECT_A,
        agent_run_id=RUN_A,
        thread_id=str(RUN_A),
        graph_key="lumi.main",
        graph_version="1.0.0",
        code_git_sha="node28-db-fixture",
        status=RunStatus.WAITING_USER,
        checkpoint_id="checkpoint-1",
        checkpoint_namespace="",
        state={
            "run_id": str(RUN_A),
            "organization_id": str(ORG_A),
            "project_id": str(PROJECT_A),
            "brief_version": 1,
            "status": RunStatus.WAITING_USER.value,
            "budget_remaining": "10.00",
            "graph_key": "lumi.main",
            "graph_version": "1.0.0",
            "code_git_sha": "node28-db-fixture",
        },
        next_nodes=("approval_interrupt",),
        interrupts=(
            {
                "id": "interrupt-1",
                "kind": "approval",
                "node": "approval_interrupt",
                "payload": {"kind": "approval"},
                "resumable": True,
            },
        ),
        resume_version=1,
        created_at=now,
        updated_at=now,
    )
    await store.create(snapshot)

    loaded = await store.load(organization_id=ORG_A, agent_run_id=RUN_A)
    assert loaded is not None
    assert loaded.checkpoint_id == "checkpoint-1"
    assert loaded.status is RunStatus.WAITING_USER
    assert await store.load(organization_id=ORG_B, agent_run_id=RUN_A) is None

    completed = replace(
        snapshot,
        status=RunStatus.SUCCEEDED,
        checkpoint_id="checkpoint-2",
        state={**snapshot.state, "status": RunStatus.SUCCEEDED.value},
        next_nodes=(),
        interrupts=(),
        resume_version=2,
        updated_at=datetime.now(UTC),
    )
    try:
        await store.compare_and_set(
            completed,
            expected_checkpoint_id="checkpoint-1",
            expected_resume_version=99,
        )
    except ResumeVersionConflict:
        pass
    else:
        raise AssertionError("stale resume_version must fail")

    await store.compare_and_set(
        completed,
        expected_checkpoint_id="checkpoint-1",
        expected_resume_version=1,
    )
    reloaded = await store.load(organization_id=ORG_A, agent_run_id=RUN_A)
    assert reloaded is not None
    assert reloaded.status is RunStatus.SUCCEEDED
    assert reloaded.resume_version == 2

    import asyncpg

    admin = await asyncpg.connect(migration_dsn)
    try:
        status = await admin.fetchval("SELECT status FROM agent_runs WHERE id=$1", RUN_A)
        assert status == "succeeded"
    finally:
        await admin.close()


async def run(migration_dsn: str, app_dsn: str) -> None:
    await _seed(migration_dsn)
    await _exercise_store(app_dsn, migration_dsn)
    print("NODE-28 LangGraph control PostgreSQL invariants: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration-dsn", required=True)
    parser.add_argument("--app-dsn", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.migration_dsn, args.app_dsn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
