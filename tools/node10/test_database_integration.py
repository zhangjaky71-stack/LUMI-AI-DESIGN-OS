# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID

import asyncpg

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
WORKSPACE_A = UUID("01910000-0000-7000-8000-000000000021")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
PROJECT_B = UUID("01910000-0000-7000-8000-000000000032")
TASK_A1 = UUID("01910000-0000-7000-8000-000000000061")
TASK_A2 = UUID("01910000-0000-7000-8000-000000000062")
ARTIFACT_A = UUID("01910000-0000-7000-8000-000000000091")
BRANCH_A = UUID("01910000-0000-7000-8000-000000000092")
ARTIFACT_VERSION_A1 = UUID("01910000-0000-7000-8000-000000000093")
COST_A = UUID("01910000-0000-7000-8000-000000000073")

APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]


async def set_tenant(connection: asyncpg.Connection, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)", str(organization_id)
    )


async def assert_raises_sqlstate(
    expected: set[str], operation: object, *, label: str
) -> None:
    try:
        await operation  # type: ignore[misc]
    except asyncpg.PostgresError as exc:
        if exc.sqlstate not in expected:
            raise AssertionError(
                f"{label}: expected SQLSTATE {sorted(expected)}, got {exc.sqlstate}: {exc}"
            ) from exc
        return
    raise AssertionError(f"{label}: expected database rejection")


async def test_alembic_revision() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        assert revision == "20260816_0001", revision
    finally:
        await connection.close()


async def test_rls_isolation() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            rows = await connection.fetch("SELECT id, organization_id FROM projects ORDER BY id")
            assert rows
            assert {row["organization_id"] for row in rows} == {ORG_A}
            assert PROJECT_A in {row["id"] for row in rows}
            assert PROJECT_B not in {row["id"] for row in rows}

        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            rows = await connection.fetch("SELECT id, organization_id FROM projects ORDER BY id")
            assert rows
            assert {row["organization_id"] for row in rows} == {ORG_B}
            assert PROJECT_B in {row["id"] for row in rows}
            assert PROJECT_A not in {row["id"] for row in rows}
    finally:
        await connection.close()


async def test_cross_tenant_reference_guard() -> None:
    connection = await asyncpg.connect(APP_DSN)
    invalid_project = UUID("01910000-0000-7000-8000-000000000201")
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            await assert_raises_sqlstate(
                {"23514"},
                connection.execute(
                    """
                    INSERT INTO projects
                      (id, organization_id, workspace_id, name, status)
                    VALUES ($1, $2, $3, 'Cross Tenant Must Fail', 'draft')
                    """,
                    invalid_project,
                    ORG_B,
                    WORKSPACE_A,
                ),
                label="cross-tenant workspace reference",
            )
    finally:
        await connection.close()


async def test_optimistic_concurrency() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            version = await connection.fetchval(
                "SELECT version FROM projects WHERE id = $1", PROJECT_A
            )
            assert isinstance(version, int)
            result = await connection.execute(
                """
                UPDATE projects
                SET name = name, version = version + 1
                WHERE id = $1 AND version = $2
                """,
                PROJECT_A,
                version,
            )
            assert result == "UPDATE 1", result
            stale = await connection.execute(
                """
                UPDATE projects
                SET name = name, version = version + 1
                WHERE id = $1 AND version = $2
                """,
                PROJECT_A,
                version,
            )
            assert stale == "UPDATE 0", stale
    finally:
        await connection.close()


async def test_exact_money_and_idempotency() -> None:
    connection = await asyncpg.connect(APP_DSN)
    duplicate_operation = UUID("01910000-0000-7000-8000-000000000202")
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            amount = await connection.fetchval(
                "SELECT amount FROM cost_ledger WHERE id = $1", COST_A
            )
            assert amount == Decimal("0.12345678")

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await assert_raises_sqlstate(
                {"23505"},
                connection.execute(
                    """
                    INSERT INTO idempotency_operations
                      (id, organization_id, idempotency_key, operation_type,
                       request_hash, status)
                    VALUES ($1, $2, 'fixture:generation:1', 'image.generate',
                            repeat('f', 64), 'started')
                    """,
                    duplicate_operation,
                    ORG_A,
                ),
                label="duplicate paid-operation idempotency key",
            )
    finally:
        await connection.close()


async def test_task_dag_cycle_guard() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await assert_raises_sqlstate(
                {"23514"},
                connection.execute(
                    """
                    INSERT INTO task_dependencies
                      (organization_id, task_id, depends_on_task_id)
                    VALUES ($1, $2, $3)
                    """,
                    ORG_A,
                    TASK_A1,
                    TASK_A2,
                ),
                label="task DAG cycle",
            )
    finally:
        await connection.close()


async def test_artifact_lineage_cycle_guard() -> None:
    connection = await asyncpg.connect(APP_DSN)
    version2 = UUID("01910000-0000-7000-8000-000000000203")
    edge1 = UUID("01910000-0000-7000-8000-000000000204")
    edge2 = UUID("01910000-0000-7000-8000-000000000205")
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute(
                """
                INSERT INTO artifact_versions
                  (id, organization_id, artifact_id, branch_id,
                   version_number, status, content_hash)
                VALUES ($1, $2, $3, $4, 2, 'ready', repeat('9', 64))
                ON CONFLICT (artifact_id, branch_id, version_number) DO NOTHING
                """,
                version2,
                ORG_A,
                ARTIFACT_A,
                BRANCH_A,
            )
            actual_version2 = await connection.fetchval(
                """
                SELECT id FROM artifact_versions
                WHERE artifact_id = $1 AND branch_id = $2 AND version_number = 2
                """,
                ARTIFACT_A,
                BRANCH_A,
            )
            assert actual_version2 is not None
            await connection.execute(
                """
                INSERT INTO artifact_edges
                  (id, organization_id, from_artifact_version_id,
                   to_artifact_version_id, edge_type)
                VALUES ($1, $2, $3, $4, 'EDITED_FROM')
                ON CONFLICT DO NOTHING
                """,
                edge1,
                ORG_A,
                ARTIFACT_VERSION_A1,
                actual_version2,
            )

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            actual_version2 = await connection.fetchval(
                """
                SELECT id FROM artifact_versions
                WHERE artifact_id = $1 AND branch_id = $2 AND version_number = 2
                """,
                ARTIFACT_A,
                BRANCH_A,
            )
            await assert_raises_sqlstate(
                {"23514"},
                connection.execute(
                    """
                    INSERT INTO artifact_edges
                      (id, organization_id, from_artifact_version_id,
                       to_artifact_version_id, edge_type)
                    VALUES ($1, $2, $3, $4, 'EDITED_FROM')
                    """,
                    edge2,
                    ORG_A,
                    actual_version2,
                    ARTIFACT_VERSION_A1,
                ),
                label="artifact lineage cycle",
            )
    finally:
        await connection.close()


async def test_approved_version_and_ledger_immutability() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            status = await connection.fetchval(
                "SELECT status FROM artifact_versions WHERE id = $1", ARTIFACT_VERSION_A1
            )
            if status == "ready":
                await connection.execute(
                    "UPDATE artifact_versions SET status = 'approved' WHERE id = $1",
                    ARTIFACT_VERSION_A1,
                )
            elif status != "approved":
                raise AssertionError(f"unexpected seeded artifact status: {status}")

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await assert_raises_sqlstate(
                {"55000"},
                connection.execute(
                    "UPDATE artifact_versions SET content_hash = repeat('8', 64) WHERE id = $1",
                    ARTIFACT_VERSION_A1,
                ),
                label="approved artifact version mutation",
            )

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await assert_raises_sqlstate(
                {"42501", "55000"},
                connection.execute(
                    "UPDATE cost_ledger SET amount = amount + 1 WHERE id = $1", COST_A
                ),
                label="cost ledger mutation",
            )
    finally:
        await connection.close()


async def test_outbox_atomic_rollback() -> None:
    connection = await asyncpg.connect(APP_DSN)
    temp_project = UUID("01910000-0000-7000-8000-000000000206")
    temp_event = UUID("01910000-0000-7000-8000-000000000207")
    try:
        try:
            async with connection.transaction():
                await set_tenant(connection, ORG_A)
                await connection.execute(
                    """
                    INSERT INTO projects
                      (id, organization_id, workspace_id, name, status)
                    VALUES ($1, $2, $3, 'Rollback Project', 'draft')
                    """,
                    temp_project,
                    ORG_A,
                    WORKSPACE_A,
                )
                await connection.execute(
                    """
                    INSERT INTO outbox_events
                      (id, organization_id, event_type, aggregate_type,
                       aggregate_id, payload_json)
                    VALUES ($1, $2, 'project.created', 'project', $3, '{}'::jsonb)
                    """,
                    temp_event,
                    ORG_A,
                    temp_project,
                )
                raise RuntimeError("intentional rollback")
        except RuntimeError as exc:
            assert str(exc) == "intentional rollback"

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            project_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM projects WHERE id = $1)", temp_project
            )
            event_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM outbox_events WHERE id = $1)", temp_event
            )
            assert project_exists is False
            assert event_exists is False
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        test_alembic_revision,
        test_rls_isolation,
        test_cross_tenant_reference_guard,
        test_optimistic_concurrency,
        test_exact_money_and_idempotency,
        test_task_dag_cycle_guard,
        test_artifact_lineage_cycle_guard,
        test_approved_version_and_ledger_immutability,
        test_outbox_atomic_rollback,
    )
    for test in tests:
        await test()
        print(f"PASS {test.__name__}")
    print(f"NODE-10 PostgreSQL integration PASS: {len(tests)} invariant groups")


if __name__ == "__main__":
    asyncio.run(main())
