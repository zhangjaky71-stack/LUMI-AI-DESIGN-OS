# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from lumi_api.domain.ids import new_uuid7
from lumi_api.idempotency import (
    CompensationMode,
    OperationRequest,
    PostgresTransactionalSideEffectGateway,
    SideEffectKind,
    SideEffectOutcome,
    canonical_request_hash,
)

ORG = UUID("01910000-0000-7000-8000-000000000001")
NOW = datetime(2026, 8, 16, 9, 55, tzinfo=UTC)
APP_DSN = os.environ["LUMI_DATABASE_APP_URL"]
MIGRATION_DSN = os.environ["LUMI_DATABASE_MIGRATION_URL_ASYNCPG"]
KEY = "node20-transaction-crash-key"
METRIC = "node20.transactional.effect"


class SimulatedHardCrash(BaseException):
    pass


async def cleanup() -> None:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        async with connection.transaction():
            await connection.execute(
                "DELETE FROM usage_counters WHERE period_key='node20-tx' AND metric_key=$1",
                METRIC,
            )
            await connection.execute(
                "DELETE FROM idempotency_operations WHERE idempotency_key=$1",
                KEY,
            )
    finally:
        await connection.close()


async def count_effects() -> int:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        return int(
            await connection.fetchval(
                """
                SELECT count(*) FROM usage_counters
                WHERE organization_id=$1 AND period_key='node20-tx' AND metric_key=$2
                """,
                ORG,
                METRIC,
            )
        )
    finally:
        await connection.close()


async def count_operations() -> int:
    connection = await asyncpg.connect(MIGRATION_DSN)
    try:
        return int(
            await connection.fetchval(
                """
                SELECT count(*) FROM idempotency_operations
                WHERE organization_id=$1 AND operation_type='db.test.atomic'
                  AND idempotency_key=$2
                """,
                ORG,
                KEY,
            )
        )
    finally:
        await connection.close()


async def main() -> None:
    await cleanup()
    gateway = PostgresTransactionalSideEffectGateway(APP_DSN)
    request = OperationRequest(
        organization_id=ORG,
        operation_type="db.test.atomic",
        idempotency_key=KEY,
        request_hash=canonical_request_hash({"metric": METRIC, "quantity": 1}),
        business_scope_id="node20-transactional-fixture",
        side_effect_kind=SideEffectKind.GENERIC_WRITE,
        compensation_mode=CompensationMode.COMPENSATABLE,
    )

    async def crashing_effect(connection, _operation_id):
        await connection.execute(
            """
            INSERT INTO usage_counters(
              id,organization_id,period_key,metric_key,quantity,unit
            ) VALUES($1,$2,'node20-tx',$3,1,'effect')
            """,
            new_uuid7(),
            ORG,
            METRIC,
        )
        raise SimulatedHardCrash("crash before outer transaction commit")

    try:
        await gateway.execute(
            request,
            crashing_effect,
            lease_owner="db-worker-crash",
            now=NOW,
        )
    except SimulatedHardCrash:
        pass
    else:
        raise AssertionError("hard crash fixture did not crash")

    assert await count_effects() == 0
    assert await count_operations() == 0

    async def successful_effect(connection, operation_id):
        await connection.execute(
            """
            INSERT INTO usage_counters(
              id,organization_id,period_key,metric_key,quantity,unit
            ) VALUES($1,$2,'node20-tx',$3,1,'effect')
            """,
            new_uuid7(),
            ORG,
            METRIC,
        )
        return SideEffectOutcome(
            result={"operation_id": str(operation_id), "effect": "committed"},
            response_status=201,
        )

    first = await gateway.execute(
        request,
        successful_effect,
        lease_owner="db-worker-success",
        now=NOW,
    )
    assert first.replayed is False
    assert await count_effects() == 1
    assert await count_operations() == 1

    replay = await gateway.execute(
        request,
        successful_effect,
        lease_owner="db-worker-replay",
        now=NOW,
    )
    assert replay.replayed is True
    assert replay.operation_id == first.operation_id
    assert await count_effects() == 1
    print("NODE20_TRANSACTIONAL_DB_GATEWAY_PASS")
    await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
