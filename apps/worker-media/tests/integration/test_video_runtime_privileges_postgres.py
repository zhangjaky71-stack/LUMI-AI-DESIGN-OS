from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 with migrated local PostgreSQL",
)


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def test_video_runtime_privileges_preserve_durable_history() -> None:
    async def run() -> None:
        connection = await asyncpg.connect(_dsn())
        try:
            for table in ("video_generation_jobs", "video_provider_jobs"):
                assert await connection.fetchval(
                    "SELECT has_table_privilege(current_user, $1::text, 'SELECT')", table
                ) is True
                assert await connection.fetchval(
                    "SELECT has_table_privilege(current_user, $1::text, 'INSERT')", table
                ) is True
                assert await connection.fetchval(
                    "SELECT has_table_privilege(current_user, $1::text, 'UPDATE')", table
                ) is True
                assert await connection.fetchval(
                    "SELECT has_table_privilege(current_user, $1::text, 'DELETE')", table
                ) is False

            assert await connection.fetchval(
                "SELECT has_table_privilege(current_user, 'cost_ledger', 'SELECT')"
            ) is True
            assert await connection.fetchval(
                "SELECT has_table_privilege(current_user, 'cost_ledger', 'UPDATE')"
            ) is False
            assert await connection.fetchval(
                "SELECT has_table_privilege(current_user, 'cost_ledger', 'DELETE')"
            ) is False

            immutable = await connection.fetchval(
                """
                SELECT count(*)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public'
                  AND NOT t.tgisinternal
                  AND c.relname = ANY($1::text[])
                  AND t.tgname = ('trg_' || c.relname || '_immutable')
                """,
                ["cost_ledger", "artifact_edges", "artifact_files", "artifact_provenance"],
            )
            assert immutable == 4
        finally:
            await connection.close()

    asyncio.run(run())
