# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
USER_A = UUID("01910000-0000-7000-8000-000000000011")
API_TOKEN_A = UUID("01910000-0000-7000-8000-000000000301")
SECURITY_EVENT = UUID("01910000-0000-7000-8000-000000000302")
APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]


async def set_tenant(connection: asyncpg.Connection, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)",
        str(organization_id),
    )


async def assert_database_rejects(operation: object, *, label: str) -> None:
    try:
        await operation  # type: ignore[misc]
    except asyncpg.PostgresError:
        return
    raise AssertionError(f"{label}: expected PostgreSQL rejection")


async def test_schema_objects_and_head() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        assert revision == "20260816_0002", revision
        for table in (
            "password_credentials",
            "auth_sessions",
            "auth_one_time_tokens",
            "api_tokens",
            "auth_security_events",
        ):
            present = await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", table)
            assert present is True, table
    finally:
        await connection.close()


async def test_argon_and_hash_database_guards() -> None:
    connection = await asyncpg.connect(APP_DSN)
    now = datetime.now(UTC)
    try:
        await connection.execute("DELETE FROM password_credentials WHERE user_id = $1", USER_A)
        await connection.execute(
            """
            INSERT INTO password_credentials(user_id, password_hash, algorithm, changed_at)
            VALUES ($1, '$argon2id$v=19$m=65536,t=3,p=4$fixture$fixture', 'argon2id', $2)
            """,
            USER_A,
            now,
        )
        await assert_database_rejects(
            connection.execute(
                """
                UPDATE password_credentials
                SET password_hash = 'plaintext-password'
                WHERE user_id = $1
                """,
                USER_A,
            ),
            label="plaintext password credential",
        )
        await assert_database_rejects(
            connection.execute(
                """
                INSERT INTO auth_sessions(
                  session_hash, user_id, created_at, expires_at,
                  last_seen_at, recent_auth_at
                ) VALUES ('not-a-sha', $1, $2, $3, $2, $2)
                """,
                USER_A,
                now,
                now + timedelta(hours=1),
            ),
            label="non-hash session key",
        )
    finally:
        await connection.close()


async def test_api_token_rls() -> None:
    connection = await asyncpg.connect(APP_DSN)
    now = datetime.now(UTC)
    token_hash = "a" * 64
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute(
                """
                INSERT INTO api_tokens(
                  id, organization_id, name, prefix, secret_hash,
                  scopes_json, created_by_user_id, created_at
                ) VALUES ($1, $2, 'fixture-token', 'fixturea1', $3,
                          '["project.read"]'::jsonb, $4, $5)
                ON CONFLICT (id) DO NOTHING
                """,
                API_TOKEN_A,
                ORG_A,
                token_hash,
                USER_A,
                now,
            )
            visible_a = await connection.fetchval(
                "SELECT count(*) FROM api_tokens WHERE id = $1", API_TOKEN_A
            )
            assert visible_a == 1

        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            visible_b = await connection.fetchval(
                "SELECT count(*) FROM api_tokens WHERE id = $1", API_TOKEN_A
            )
            assert visible_b == 0
    finally:
        await connection.close()


async def test_auth_security_events_are_pre_tenant_and_append_only() -> None:
    connection = await asyncpg.connect(APP_DSN)
    now = datetime.now(UTC)
    try:
        await connection.execute(
            """
            INSERT INTO auth_security_events(
              id, category, organization_id, occurred_at, metadata_json
            ) VALUES ($1, 'LOGIN_FAILURE', NULL, $2, '{"category":"invalid_credentials"}'::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            SECURITY_EVENT,
            now,
        )
        row = await connection.fetchrow(
            "SELECT organization_id, category FROM auth_security_events WHERE id = $1",
            SECURITY_EVENT,
        )
        assert row is not None
        assert row["organization_id"] is None
        assert row["category"] == "LOGIN_FAILURE"
        await assert_database_rejects(
            connection.execute(
                "UPDATE auth_security_events SET category = 'MUTATED' WHERE id = $1",
                SECURITY_EVENT,
            ),
            label="auth security event update",
        )
    finally:
        await connection.close()


async def test_role_constraint_is_node16_matrix() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    invalid_id = UUID("01910000-0000-7000-8000-000000000303")
    try:
        await assert_database_rejects(
            connection.execute(
                """
                INSERT INTO organization_members(id, organization_id, user_id, role)
                VALUES ($1, $2, $3, 'member')
                """,
                invalid_id,
                ORG_A,
                USER_A,
            ),
            label="legacy member role",
        )
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        test_schema_objects_and_head,
        test_argon_and_hash_database_guards,
        test_api_token_rls,
        test_auth_security_events_are_pre_tenant_and_append_only,
        test_role_constraint_is_node16_matrix,
    )
    for test in tests:
        await test()
        print(f"PASS {test.__name__}")
    print(f"NODE-16 PostgreSQL auth integration PASS: {len(tests)} invariant groups")


if __name__ == "__main__":
    asyncio.run(main())
