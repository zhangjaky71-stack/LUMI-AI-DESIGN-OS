# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
PROJECT_B = UUID("01910000-0000-7000-8000-000000000032")
ASSET_A = UUID("01910000-0000-7000-8000-000000000051")
USER_A = UUID("01910000-0000-7000-8000-000000000011")
UPLOAD_A = UUID("01910000-0000-7000-8000-000000000501")
FILE_A = UUID("01910000-0000-7000-8000-000000000502")
REPORT_A = UUID("01910000-0000-7000-8000-000000000503")
APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]


async def set_tenant(connection: asyncpg.Connection, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)",
        str(organization_id),
    )


async def reject(
    connection: asyncpg.Connection,
    operation,
    *,
    sqlstates: set[str],
    label: str,
) -> None:
    try:
        async with connection.transaction():
            await operation
    except asyncpg.PostgresError as exc:
        if exc.sqlstate not in sqlstates:
            raise AssertionError(
                f"{label}: expected {sorted(sqlstates)}, got {exc.sqlstate}: {exc}"
            ) from exc
        return
    raise AssertionError(f"{label}: expected PostgreSQL rejection")


async def test_head_and_asset_storage_objects() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        assert revision == "20260816_0004", revision
        for table in ("asset_upload_sessions", "asset_validation_reports"):
            assert await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", table)
        row = await connection.fetchrow(
            "SELECT declared_mime_type, original_filename, status FROM assets WHERE id=$1",
            ASSET_A,
        )
        assert row is not None
        assert row["declared_mime_type"] == "image/png"
        assert row["original_filename"] == "unknown"
        assert row["status"] == "ready"
    finally:
        await connection.close()


async def insert_valid_upload(connection: asyncpg.Connection) -> None:
    now = datetime.now(UTC)
    key = f"org/{ORG_A}/project/{PROJECT_A}/asset/{ASSET_A}/original/{FILE_A}"
    await connection.execute(
        """
        INSERT INTO asset_upload_sessions(
          id,organization_id,project_id,asset_id,file_id,bucket,object_key,
          original_filename,declared_mime_type,expected_size,
          expected_checksum_sha256,mode,status,created_at,expires_at,completed_at
        ) VALUES(
          $1,$2,$3,$4,$5,'lumi-assets',$6,'fixture.png','image/png',1024,
          repeat('a',64),'single_put','verifying',$7,$8,$7
        ) ON CONFLICT (id) DO NOTHING
        """,
        UPLOAD_A,
        ORG_A,
        PROJECT_A,
        ASSET_A,
        FILE_A,
        key,
        now,
        now + timedelta(minutes=15),
    )


async def test_upload_rls_and_canonical_key_guard() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await insert_valid_upload(connection)
            assert await connection.fetchval(
                "SELECT count(*) FROM asset_upload_sessions WHERE id=$1", UPLOAD_A
            ) == 1
        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            assert await connection.fetchval(
                "SELECT count(*) FROM asset_upload_sessions WHERE id=$1", UPLOAD_A
            ) == 0
    finally:
        await connection.close()

    migration = await asyncpg.connect(MIGRATION_DSN)
    try:
        bad_id = UUID("01910000-0000-7000-8000-000000000504")
        bad_file = UUID("01910000-0000-7000-8000-000000000505")
        await reject(
            migration,
            migration.execute(
                """
                INSERT INTO asset_upload_sessions(
                  id,organization_id,project_id,asset_id,file_id,bucket,object_key,
                  original_filename,declared_mime_type,expected_size,
                  expected_checksum_sha256,mode,status,expires_at
                ) VALUES(
                  $1,$2,$3,$4,$5,'lumi-assets','user-controlled/key','x.png',
                  'image/png',1,repeat('b',64),'single_put','pending',now()+interval '15 min'
                )
                """,
                bad_id,
                ORG_A,
                PROJECT_A,
                ASSET_A,
                bad_file,
            ),
            sqlstates={"23514"},
            label="noncanonical object key",
        )
        cross_id = UUID("01910000-0000-7000-8000-000000000506")
        cross_file = UUID("01910000-0000-7000-8000-000000000507")
        cross_key = f"org/{ORG_B}/project/{PROJECT_B}/asset/{ASSET_A}/original/{cross_file}"
        await reject(
            migration,
            migration.execute(
                """
                INSERT INTO asset_upload_sessions(
                  id,organization_id,project_id,asset_id,file_id,bucket,object_key,
                  original_filename,declared_mime_type,expected_size,
                  expected_checksum_sha256,mode,status,expires_at
                ) VALUES(
                  $1,$2,$3,$4,$5,'lumi-assets',$6,'x.png','image/png',1,
                  repeat('c',64),'single_put','pending',now()+interval '15 min'
                )
                """,
                cross_id,
                ORG_B,
                PROJECT_B,
                ASSET_A,
                cross_file,
                cross_key,
            ),
            sqlstates={"23514"},
            label="cross-tenant upload relationship",
        )
    finally:
        await migration.close()


async def test_validation_report_is_append_only_and_tenant_scoped() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await insert_valid_upload(connection)
            await connection.execute(
                """
                INSERT INTO asset_validation_reports(
                  id,organization_id,asset_id,upload_session_id,
                  expected_checksum_sha256,actual_checksum_sha256,
                  expected_size,actual_size,sniffed_mime_type,media_kind,
                  scan_status,scan_engine,accepted,reason_codes_json,metadata_json
                ) VALUES(
                  $1,$2,$3,$4,repeat('a',64),repeat('a',64),1024,1024,
                  'image/png','image','clean','clamd',true,'[]'::jsonb,'{}'::jsonb
                ) ON CONFLICT (id) DO NOTHING
                """,
                REPORT_A,
                ORG_A,
                ASSET_A,
                UPLOAD_A,
            )
            assert await connection.fetchval(
                "SELECT accepted FROM asset_validation_reports WHERE id=$1", REPORT_A
            ) is True
            await reject(
                connection,
                connection.execute(
                    "UPDATE asset_validation_reports SET accepted=false WHERE id=$1",
                    REPORT_A,
                ),
                sqlstates={"42501"},
                label="validation report update",
            )
        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            assert await connection.fetchval(
                "SELECT count(*) FROM asset_validation_reports WHERE id=$1", REPORT_A
            ) == 0
    finally:
        await connection.close()


async def test_rights_assertion_does_not_grant_commercial_use() -> None:
    connection = await asyncpg.connect(APP_DSN)
    rights_id = UUID("01910000-0000-7000-8000-000000000508")
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute("DELETE FROM asset_rights WHERE asset_id=$1", ASSET_A)
            await connection.execute(
                """
                INSERT INTO asset_rights(
                  id,organization_id,asset_id,rights_level,assertion,
                  commercial_use,attribution_required,asserted_by,asserted_at
                ) VALUES($1,$2,$3,'owned','USER_OWNED',false,false,$4,now())
                """,
                rights_id,
                ORG_A,
                ASSET_A,
                USER_A,
            )
            row = await connection.fetchrow(
                "SELECT assertion,commercial_use FROM asset_rights WHERE asset_id=$1",
                ASSET_A,
            )
            assert row is not None
            assert row["assertion"] == "USER_OWNED"
            assert row["commercial_use"] is False
    finally:
        await connection.close()


async def test_asset_status_and_file_metadata_contract() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute(
                "UPDATE assets SET status='verifying' WHERE id=$1",
                ASSET_A,
            )
            assert await connection.fetchval(
                "SELECT status FROM assets WHERE id=$1", ASSET_A
            ) == "verifying"
            await connection.execute("UPDATE assets SET status='ready' WHERE id=$1", ASSET_A)
            row = await connection.fetchrow(
                """
                SELECT role,mime_type,verified_at
                FROM asset_files WHERE asset_id=$1 ORDER BY created_at LIMIT 1
                """,
                ASSET_A,
            )
            assert row is not None
            assert row["role"] == "original"
            assert row["mime_type"] == "image/png"
            assert row["verified_at"] is not None
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        test_head_and_asset_storage_objects,
        test_upload_rls_and_canonical_key_guard,
        test_validation_report_is_append_only_and_tenant_scoped,
        test_rights_assertion_does_not_grant_commercial_use,
        test_asset_status_and_file_metadata_contract,
    )
    for test in tests:
        await test()
        print(f"PASS {test.__name__}")
    print(f"NODE-18 PostgreSQL asset storage PASS: {len(tests)} invariant groups")


if __name__ == "__main__":
    asyncio.run(main())
