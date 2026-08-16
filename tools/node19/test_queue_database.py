# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
JOB_A = UUID("01910000-0000-7000-8000-000000000801")
EVENT_A = UUID("01910000-0000-7000-8000-000000000802")
DLQ_A = UUID("01910000-0000-7000-8000-000000000803")
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]
APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]
NOW = datetime(2026, 8, 16, 9, 5, tzinfo=UTC)


async def set_tenant(connection: asyncpg.Connection, org: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)",
        str(org),
    )


async def reject(awaitable, *, sqlstates: set[str], label: str) -> None:
    try:
        await awaitable
    except asyncpg.PostgresError as exc:
        if exc.sqlstate not in sqlstates:
            raise AssertionError(
                f"{label}: expected {sorted(sqlstates)}, got {exc.sqlstate}: {exc}"
            ) from exc
        return
    raise AssertionError(f"{label}: expected rejection")


async def test_head_and_objects() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "20260816_0005"
        for table in ("runtime_jobs", "dead_letter_records"):
            assert await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", table)
        columns = {
            row["column_name"]
            for row in await connection.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='outbox_events'
                """
            )
        }
        assert {"last_publish_attempt_at", "next_publish_at", "last_publish_error"} <= columns
    finally:
        await connection.close()


async def test_runtime_job_rls_and_same_tenant_guard() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute(
                """
                INSERT INTO runtime_jobs(
                  id,organization_id,project_id,job_kind,status,max_attempts,input_json
                ) VALUES($1,$2,$3,'asset.validate','pending',4,$4::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                JOB_A,
                ORG_A,
                PROJECT_A,
                json.dumps({"job_id": str(JOB_A), "resource_id": str(EVENT_A)}),
            )
            assert await connection.fetchval(
                "SELECT status FROM runtime_jobs WHERE id=$1", JOB_A
            ) == "pending"

        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            assert await connection.fetchval(
                "SELECT count(*) FROM runtime_jobs WHERE id=$1", JOB_A
            ) == 0
            async with connection.transaction():
                await reject(
                    connection.execute(
                        """
                        INSERT INTO runtime_jobs(
                          id,organization_id,project_id,job_kind,status,input_json
                        ) VALUES($1,$2,$3,'image.transform','pending','{}'::jsonb)
                        """,
                        UUID("01910000-0000-7000-8000-000000000899"),
                        ORG_B,
                        PROJECT_A,
                    ),
                    sqlstates={"23503", "42501"},
                    label="cross tenant runtime job",
                )
    finally:
        await connection.close()


async def test_inbox_receipt_rolls_back_with_effect() -> None:
    connection = await asyncpg.connect(APP_DSN)
    metric = "node19.inbox.effect"
    try:
        try:
            async with connection.transaction():
                await set_tenant(connection, ORG_A)
                inserted = await connection.fetchval(
                    """
                    INSERT INTO inbox_events(event_id,consumer,organization_id)
                    VALUES($1,'node19-db.v1',$2)
                    ON CONFLICT (event_id,consumer) DO NOTHING
                    RETURNING event_id
                    """,
                    EVENT_A,
                    ORG_A,
                )
                assert inserted == EVENT_A
                await connection.execute(
                    """
                    INSERT INTO usage_counters(id,organization_id,period_key,metric_key,quantity,unit)
                    VALUES($1,$2,'node19',$3,1,'effect')
                    ON CONFLICT (organization_id,period_key,metric_key)
                    DO UPDATE SET quantity=usage_counters.quantity+1
                    """,
                    UUID("01910000-0000-7000-8000-000000000804"),
                    ORG_A,
                    metric,
                )
                raise RuntimeError("intentional rollback")
        except RuntimeError as exc:
            assert str(exc) == "intentional rollback"

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            inserted = await connection.fetchval(
                """
                INSERT INTO inbox_events(event_id,consumer,organization_id)
                VALUES($1,'node19-db.v1',$2)
                ON CONFLICT (event_id,consumer) DO NOTHING
                RETURNING event_id
                """,
                EVENT_A,
                ORG_A,
            )
            assert inserted == EVENT_A
            await connection.execute(
                """
                INSERT INTO usage_counters(id,organization_id,period_key,metric_key,quantity,unit)
                VALUES($1,$2,'node19',$3,1,'effect')
                ON CONFLICT (organization_id,period_key,metric_key)
                DO UPDATE SET quantity=usage_counters.quantity+1
                """,
                UUID("01910000-0000-7000-8000-000000000805"),
                ORG_A,
                metric,
            )

        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            duplicate = await connection.fetchval(
                """
                INSERT INTO inbox_events(event_id,consumer,organization_id)
                VALUES($1,'node19-db.v1',$2)
                ON CONFLICT (event_id,consumer) DO NOTHING
                RETURNING event_id
                """,
                EVENT_A,
                ORG_A,
            )
            assert duplicate is None
            assert await connection.fetchval(
                """
                SELECT quantity FROM usage_counters
                WHERE organization_id=$1 AND period_key='node19' AND metric_key=$2
                """,
                ORG_A,
                metric,
            ) == 1
    finally:
        await connection.close()


async def test_dead_letter_rls_and_outbox_retry_columns() -> None:
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute(
                """
                INSERT INTO dead_letter_records(
                  id,organization_id,message_id,message_kind,source_queue,consumer,
                  exchange_name,routing_key,error_category,error_code,error_message,
                  attempts,payload_json,first_failed_at,last_failed_at,status
                ) VALUES(
                  $1,$2,$3,'domain_event','lumi.domain.node19.v1','node19.v1',
                  'lumi.domain','lumi.project.created.v1','permanent','FIXTURE','fixture',
                  1,'{}'::jsonb,$4,$4,'open'
                ) ON CONFLICT (id) DO NOTHING
                """,
                DLQ_A,
                ORG_A,
                EVENT_A,
                NOW,
            )
            assert await connection.fetchval(
                "SELECT status FROM dead_letter_records WHERE id=$1", DLQ_A
            ) == "open"

        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            assert await connection.fetchval(
                "SELECT count(*) FROM dead_letter_records WHERE id=$1", DLQ_A
            ) == 0
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        test_head_and_objects,
        test_runtime_job_rls_and_same_tenant_guard,
        test_inbox_receipt_rolls_back_with_effect,
        test_dead_letter_rls_and_outbox_retry_columns,
    )
    for test in tests:
        await test()
        print(f"PASS {test.__name__}")
    print(f"NODE-19 PostgreSQL PASS: {len(tests)} invariant groups")


if __name__ == "__main__":
    asyncio.run(main())
