# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from lumi_api.domain.ids import new_uuid7
from lumi_api.idempotency import (
    AcquireAction,
    CompensationMode,
    OperationRequest,
    SideEffectKind,
    canonical_request_hash,
)
from lumi_api.idempotency.postgres import PostgresIdempotencyStore

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
NOW = datetime(2026, 8, 16, 9, 45, tzinfo=UTC)
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]
APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]


async def set_tenant(connection: asyncpg.Connection, org: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)", str(org)
    )


async def cleanup_unreferenced_claim_fixtures() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        async with connection.transaction():
            await connection.execute(
                """
                DELETE FROM idempotency_operations
                WHERE idempotency_key IN (
                  'node20-concurrent-key',
                  'node20-cross-operation-key'
                )
                """
            )
    finally:
        await connection.close()


async def expect_postgres_error(awaitable, *, sqlstates: set[str], label: str) -> None:
    try:
        await awaitable
    except asyncpg.PostgresError as exc:
        if exc.sqlstate not in sqlstates:
            raise AssertionError(
                f"{label}: expected {sorted(sqlstates)}, got {exc.sqlstate}: {exc}"
            ) from exc
        return
    raise AssertionError(f"{label}: expected database rejection")


def operation_request(
    *,
    key: str = "node20-db-shared-key",
    operation_type: str = "api.project.create",
    prompt: str = "one",
    paid: bool = False,
    lease_seconds: int = 60,
) -> OperationRequest:
    return OperationRequest(
        organization_id=ORG_A,
        operation_type=operation_type,
        idempotency_key=key,
        request_hash=canonical_request_hash({"project_id": PROJECT_A, "prompt": prompt}),
        business_scope_id=str(PROJECT_A),
        side_effect_kind=(
            SideEffectKind.PAID_MODEL_INVOCATION
            if paid
            else SideEffectKind.GENERIC_WRITE
        ),
        compensation_mode=CompensationMode.NON_COMPENSATABLE,
        paid=paid,
        lease_seconds=lease_seconds,
    )


async def test_head_and_schema() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        assert (
            await connection.fetchval("SELECT version_num FROM alembic_version")
            == "20260816_0006"
        )
        columns = {
            row["column_name"]
            for row in await connection.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='idempotency_operations'
                """
            )
        }
        assert {
            "lease_owner",
            "lease_expires_at",
            "provider_request_id",
            "result_ref",
            "response_status",
            "error_category",
            "recovery_state",
            "completed_at",
            "version",
        } <= columns
        assert await connection.fetchval(
            """
            SELECT EXISTS(
              SELECT 1 FROM pg_indexes
              WHERE schemaname='public'
                AND indexname='uq_cost_ledger_charge_operation'
            )
            """
        )
    finally:
        await connection.close()


async def test_concurrent_claim_and_hash_conflict() -> None:
    store = PostgresIdempotencyStore(APP_DSN)
    req = operation_request(key="node20-concurrent-key")
    first, second = await asyncio.gather(
        store.acquire(req, lease_owner="worker-a", now=NOW),
        store.acquire(req, lease_owner="worker-b", now=NOW),
    )
    assert {first.action, second.action} == {AcquireAction.EXECUTE, AcquireAction.WAIT}
    assert len({first.operation.id, second.operation.id}) == 1

    conflict = await store.acquire(
        operation_request(key="node20-concurrent-key", prompt="different"),
        lease_owner="worker-c",
        now=NOW + timedelta(seconds=1),
    )
    assert conflict.action is AcquireAction.CONFLICT


async def test_operation_type_scopes_same_client_key_and_stale_recovery() -> None:
    store = PostgresIdempotencyStore(APP_DSN)
    shared = "node20-cross-operation-key"
    project = await store.acquire(
        operation_request(
            key=shared,
            operation_type="api.project.create",
            lease_seconds=5,
        ),
        lease_owner="project-worker",
        now=NOW,
    )
    task = await store.acquire(
        operation_request(
            key=shared,
            operation_type="api.task.create",
            lease_seconds=5,
        ),
        lease_owner="task-worker",
        now=NOW,
    )
    assert project.action is AcquireAction.EXECUTE
    assert task.action is AcquireAction.EXECUTE
    assert project.operation.id != task.operation.id

    recovered = await store.acquire(
        operation_request(
            key=shared,
            operation_type="api.project.create",
            lease_seconds=5,
        ),
        lease_owner="recovery-worker",
        now=NOW + timedelta(seconds=6),
    )
    assert recovered.action is AcquireAction.RECOVER
    assert recovered.operation.id == project.operation.id
    assert recovered.operation.lease_owner == "recovery-worker"


async def test_rls_and_cost_charge_uniqueness() -> None:
    operation_id = new_uuid7()
    first_charge_id = new_uuid7()
    second_charge_id = new_uuid7()
    idempotency_key = f"node20-charge-{new_uuid7()}"
    connection = await asyncpg.connect(APP_DSN)
    try:
        async with connection.transaction():
            await set_tenant(connection, ORG_A)
            await connection.execute(
                """
                INSERT INTO idempotency_operations(
                  id,organization_id,idempotency_key,operation_type,request_hash,
                  side_effect_kind,compensation_mode,paid,status,recovery_state,
                  created_at,updated_at,completed_at,version
                ) VALUES(
                  $1,$2,$3,'billing.charge',$4,
                  'billing_charge','reversible_by_new_operation',true,
                  'succeeded','none',$5,$5,$5,1
                )
                """,
                operation_id,
                ORG_A,
                idempotency_key,
                "a" * 64,
                NOW,
            )
            await connection.execute(
                """
                INSERT INTO cost_ledger(
                  id,organization_id,project_id,operation_id,
                  entry_type,amount,currency,occurred_at
                ) VALUES($1,$2,$3,$4,'charge',$5,'USD',$6)
                """,
                first_charge_id,
                ORG_A,
                PROJECT_A,
                operation_id,
                Decimal("1.25"),
                NOW,
            )
            assert (
                await connection.fetchval(
                    """
                    SELECT count(*) FROM cost_ledger
                    WHERE organization_id=$1 AND operation_id=$2
                      AND entry_type='charge'
                    """,
                    ORG_A,
                    operation_id,
                )
                == 1
            )
            async with connection.transaction():
                await expect_postgres_error(
                    connection.execute(
                        """
                        INSERT INTO cost_ledger(
                          id,organization_id,project_id,operation_id,
                          entry_type,amount,currency,occurred_at
                        ) VALUES($1,$2,$3,$4,'charge',$5,'USD',$6)
                        """,
                        second_charge_id,
                        ORG_A,
                        PROJECT_A,
                        operation_id,
                        Decimal("1.25"),
                        NOW,
                    ),
                    sqlstates={"23505"},
                    label="duplicate charge for same operation",
                )

        async with connection.transaction():
            await set_tenant(connection, ORG_B)
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM idempotency_operations WHERE id=$1",
                    operation_id,
                )
                == 0
            )
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        test_head_and_schema,
        test_concurrent_claim_and_hash_conflict,
        test_operation_type_scopes_same_client_key_and_stale_recovery,
        test_rls_and_cost_charge_uniqueness,
    )
    await cleanup_unreferenced_claim_fixtures()
    try:
        for test in tests:
            await test()
            print(f"PASS {test.__name__}")
        print(f"NODE-20 PostgreSQL PASS: {len(tests)} invariant groups")
    finally:
        await cleanup_unreferenced_claim_fixtures()


if __name__ == "__main__":
    asyncio.run(main())
