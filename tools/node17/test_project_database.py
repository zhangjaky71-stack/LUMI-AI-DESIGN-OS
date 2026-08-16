# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import os
from uuid import UUID

import asyncpg

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
USER_A = UUID("01910000-0000-7000-8000-000000000011")
WORKSPACE_A = UUID("01910000-0000-7000-8000-000000000021")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]


async def set_tenant(connection: asyncpg.Connection, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)", str(organization_id)
    )


async def reject(operation: object, *, sqlstates: set[str], label: str) -> None:
    try:
        await operation  # type: ignore[misc]
    except asyncpg.PostgresError as exc:
        if exc.sqlstate not in sqlstates:
            raise AssertionError(
                f"{label}: expected {sorted(sqlstates)}, got {exc.sqlstate}: {exc}"
            ) from exc
        return
    raise AssertionError(f"{label}: expected PostgreSQL rejection")


async def test_head_and_project_core_objects() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        assert revision == "20260816_0003", revision
        for table in (
            "project_brief_versions",
            "project_branch_defaults",
            "project_summaries",
            "agent_run_project_context",
        ):
            assert await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", table)
        assert await connection.fetchval(
            "SELECT brief_version FROM projects WHERE id = $1", PROJECT_A
        ) == 1
    finally:
        await connection.close()


async def test_baseline_backfill_and_projection() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            brief = await connection.fetchrow(
                """
                SELECT version_number, project_id FROM project_brief_versions
                WHERE project_id = $1
                """,
                PROJECT_A,
            )
            assert brief is not None and brief["version_number"] == 1
            branch = await connection.fetchrow(
                "SELECT name FROM project_branch_defaults WHERE project_id = $1",
                PROJECT_A,
            )
            assert branch is not None and branch["name"] == "main"
            summary = await connection.fetchrow(
                "SELECT active_run_count, artifact_count FROM project_summaries WHERE project_id = $1",
                PROJECT_A,
            )
            assert summary is not None
            assert summary["active_run_count"] >= 0
            assert summary["artifact_count"] >= 0
    finally:
        await connection.close()


async def test_project_core_rls_hides_other_tenant() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            assert await connection.fetchval(
                "SELECT count(*) FROM project_brief_versions WHERE project_id = $1",
                PROJECT_A,
            ) == 0
            assert await connection.fetchval(
                "SELECT count(*) FROM project_summaries WHERE project_id = $1",
                PROJECT_A,
            ) == 0
    finally:
        await connection.close()


async def test_brief_history_is_append_only_for_app_role() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await reject(
                connection.execute(
                    "UPDATE project_brief_versions SET change_reason = 'mutated' WHERE project_id = $1",
                    PROJECT_A,
                ),
                sqlstates={"42501"},
                label="brief history update",
            )
    finally:
        await connection.close()


async def test_paid_execution_guard_blocks_archived_project() -> None:
    connection = await asyncpg.connect(APP_DSN)
    run_id = UUID("01910000-0000-7000-8000-000000000401")
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            current = await connection.fetchval("SELECT status FROM projects WHERE id = $1", PROJECT_A)
            await connection.execute(
                "UPDATE projects SET status='archived', archived_at=now() WHERE id=$1",
                PROJECT_A,
            )
            await reject(
                connection.execute(
                    """
                    INSERT INTO agent_runs(
                      id, organization_id, project_id, thread_id, graph_version,
                      agent_config_version, status, budget_amount, budget_currency
                    ) VALUES ($1, $2, $3, 'node17-archived', 'v1', 'v1', 'pending', 1.0, 'USD')
                    """,
                    run_id,
                    ORG_A,
                    PROJECT_A,
                ),
                sqlstates={"55000"},
                label="archived project agent run",
            )
            if current == "archived":
                await connection.execute(
                    "UPDATE projects SET archived_at=now() WHERE id=$1", PROJECT_A
                )
            else:
                await connection.execute(
                    "UPDATE projects SET status=$2, archived_at=NULL WHERE id=$1",
                    PROJECT_A,
                    current,
                )
    finally:
        await connection.close()


async def test_agent_run_context_freezes_brief_version() -> None:
    connection = await asyncpg.connect(APP_DSN)
    run_id = UUID("01910000-0000-7000-8000-000000000402")
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            status = await connection.fetchval("SELECT status FROM projects WHERE id=$1", PROJECT_A)
            if status in {"paused", "archived"}:
                await connection.execute(
                    "UPDATE projects SET status='active', archived_at=NULL WHERE id=$1",
                    PROJECT_A,
                )
            brief_version = await connection.fetchval(
                "SELECT brief_version FROM projects WHERE id=$1", PROJECT_A
            )
            await connection.execute(
                """
                INSERT INTO agent_runs(
                  id, organization_id, project_id, thread_id, graph_version,
                  agent_config_version, status, budget_amount, budget_currency
                ) VALUES ($1, $2, $3, 'node17-context', 'v1', 'v1', 'pending', 1.0, 'USD')
                ON CONFLICT (id) DO NOTHING
                """,
                run_id,
                ORG_A,
                PROJECT_A,
            )
            await connection.execute(
                """
                INSERT INTO agent_run_project_context(
                  organization_id, agent_run_id, project_id, project_brief_version
                ) VALUES ($1, $2, $3, $4)
                ON CONFLICT (agent_run_id) DO NOTHING
                """,
                ORG_A,
                run_id,
                PROJECT_A,
                brief_version,
            )
            frozen = await connection.fetchval(
                "SELECT project_brief_version FROM agent_run_project_context WHERE agent_run_id=$1",
                run_id,
            )
            assert frozen == brief_version
    finally:
        await connection.close()


async def test_project_create_bundle_rolls_back_atomically() -> None:
    connection = await asyncpg.connect(APP_DSN)
    project_id = UUID("01910000-0000-7000-8000-000000000410")
    brief_id = UUID("01910000-0000-7000-8000-000000000411")
    branch_id = UUID("01910000-0000-7000-8000-000000000412")
    event_id = UUID("01910000-0000-7000-8000-000000000413")
    audit_id = UUID("01910000-0000-7000-8000-000000000414")
    try:
        try:
            async with connection.transaction():
                await set_tenant(connection, ORG_A)
                await connection.execute(
                    """
                    INSERT INTO projects(
                      id, organization_id, workspace_id, name, status,
                      brief_json, brief_version, settings_json, created_by
                    ) VALUES ($1,$2,$3,'Atomic Project','draft',
                              '{"objective":"atomic"}'::jsonb,1,'{}'::jsonb,$4)
                    """,
                    project_id,
                    ORG_A,
                    WORKSPACE_A,
                    USER_A,
                )
                await connection.execute(
                    """
                    INSERT INTO project_brief_versions(
                      id, organization_id, project_id, version_number, brief_json, changed_by
                    ) VALUES ($1,$2,$3,1,'{"objective":"atomic"}'::jsonb,$4)
                    """,
                    brief_id,
                    ORG_A,
                    project_id,
                    USER_A,
                )
                await connection.execute(
                    "INSERT INTO project_branch_defaults(id,organization_id,project_id,name) VALUES($1,$2,$3,'main')",
                    branch_id,
                    ORG_A,
                    project_id,
                )
                await connection.execute(
                    "INSERT INTO project_summaries(organization_id,project_id,last_activity_at) VALUES($1,$2,now())",
                    ORG_A,
                    project_id,
                )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(
                      id,organization_id,event_type,aggregate_type,aggregate_id,payload_json
                    ) VALUES($1,$2,'project.created','project',$3,'{}'::jsonb)
                    """,
                    event_id,
                    ORG_A,
                    project_id,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_events(
                      id,organization_id,actor_type,actor_id,action,subject_type,
                      subject_id,details_json,event_hash
                    ) VALUES($1,$2,'USER',$3,'project.created','project',$4,'{}'::jsonb,repeat('a',64))
                    """,
                    audit_id,
                    ORG_A,
                    str(USER_A),
                    str(project_id),
                )
                raise RuntimeError("intentional project bundle rollback")
        except RuntimeError as exc:
            assert str(exc) == "intentional project bundle rollback"

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            assert not await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM projects WHERE id=$1)", project_id
            )
            assert not await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM outbox_events WHERE id=$1)", event_id
            )
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        test_head_and_project_core_objects,
        test_baseline_backfill_and_projection,
        test_project_core_rls_hides_other_tenant,
        test_brief_history_is_append_only_for_app_role,
        test_paid_execution_guard_blocks_archived_project,
        test_agent_run_context_freezes_brief_version,
        test_project_create_bundle_rolls_back_atomically,
    )
    for test in tests:
        await test()
        print(f"PASS {test.__name__}")
    print(f"NODE-17 PostgreSQL project core PASS: {len(tests)} invariant groups")


if __name__ == "__main__":
    asyncio.run(main())
