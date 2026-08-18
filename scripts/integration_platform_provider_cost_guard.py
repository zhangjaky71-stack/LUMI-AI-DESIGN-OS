from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from lumi_api.costs import (
    ActualCost,
    BudgetExceeded,
    BudgetReservationRequest,
    CostConfidence,
    CostContext,
    PlatformGuardedCostGateway,
)
from lumi_api.persistence.seed import ORG_ID


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


async def _insert_operation(
    connection: asyncpg.Connection,
    *,
    organization_id: UUID,
    operation_id: UUID,
    suffix: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO idempotency_operations (
            id, organization_id, idempotency_key, operation_type, status,
            request_hash, result_json, attempt_count, created_at, updated_at, version
        ) VALUES (
            $1,$2,$3,'release.platform-cost-guard','new',$4,'{}'::jsonb,0,now(),now(),1
        )
        """,
        operation_id,
        organization_id,
        f"release-platform-cost-{suffix}-{operation_id}",
        "0" * 64,
    )


def _request(organization_id: UUID, operation_id: UUID) -> BudgetReservationRequest:
    return BudgetReservationRequest(
        context=CostContext(
            organization_id=organization_id,
            operation_id=operation_id,
        ),
        provider="mock",
        model="platform-guard-v1",
        estimated_amount=Decimal("0.10"),
        currency="USD",
        pricing_snapshot_id="platform-guard-price-v1",
        confidence=CostConfidence.ESTIMATED,
        reservation_key="model:mock:platform-guard-v1",
    )


async def main_async() -> None:
    runtime_dsn = _dsn("DATABASE_URL")
    migration_dsn = _dsn("MIGRATION_DATABASE_URL")
    runtime = await asyncpg.connect(runtime_dsn)
    migration = await asyncpg.connect(migration_dsn)
    gateway = PlatformGuardedCostGateway(runtime_dsn)

    second_org = uuid4()
    operation_ids: list[UUID] = []
    original_policy = None
    handles = []
    try:
        original_policy = await migration.fetchrow(
            """
            SELECT daily_cap_usd, enabled, fail_closed, metadata_json, version
            FROM platform_provider_cost_guard
            WHERE policy_key='platform'
            """
        )
        assert original_policy is not None
        assert Decimal(original_policy["daily_cap_usd"]) == Decimal("100.00000000")
        assert original_policy["enabled"] is True
        assert original_policy["fail_closed"] is True

        await migration.execute(
            """
            INSERT INTO organizations (
                id, name, slug, status, plan, settings_json, created_at, updated_at, version
            ) VALUES (
                $1,'Release Guard Org','release-guard-' || replace($1::text,'-',''),
                'active','development','{}'::jsonb,now(),now(),1
            )
            """,
            second_org,
        )

        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        baseline_spent = Decimal(
            await runtime.fetchval(
                """
                SELECT COALESCE(sum(amount),0)
                FROM cost_ledger
                WHERE currency='USD'
                  AND cost_basis='provider_cost'
                  AND entry_type IN ('actual_cost','adjustment','reversal')
                  AND occurred_at >= $1 AND occurred_at < $2
                """,
                start,
                end,
            )
        )
        baseline_active = Decimal(
            await runtime.fetchval(
                """
                SELECT COALESCE(sum(estimated_amount),0)
                FROM cost_reservations
                WHERE currency='USD' AND status='active' AND expires_at > now()
                """
            )
        )
        test_cap = baseline_spent + baseline_active + Decimal("0.30")
        await migration.execute(
            """
            UPDATE platform_provider_cost_guard
            SET daily_cap_usd=$1, enabled=true, fail_closed=true,
                metadata_json='{"test":"integration_platform_provider_cost_guard"}'::jsonb,
                updated_at=now(), version=version+1
            WHERE policy_key='platform'
            """,
            test_cap,
        )

        # Cross-organization concurrency: six 0.10 reservations compete on one
        # platform advisory lock. Exactly three may enter the canonical ledger.
        organizations = [ORG_ID, second_org, ORG_ID, second_org, ORG_ID, second_org]
        for index, organization_id in enumerate(organizations):
            operation_id = uuid4()
            operation_ids.append(operation_id)
            await _insert_operation(
                migration,
                organization_id=organization_id,
                operation_id=operation_id,
                suffix=f"concurrent-{index}",
            )

        async def attempt(index: int):
            request = _request(organizations[index], operation_ids[index])
            try:
                return await gateway.reserve(request)
            except BudgetExceeded:
                return None

        results = await asyncio.gather(*(attempt(index) for index in range(6)))
        handles = [result for result in results if result is not None]
        assert len(handles) == 3, len(handles)
        assert {handle.request.context.organization_id for handle in handles} <= {
            ORG_ID,
            second_org,
        }

        guarded_active = Decimal(
            await runtime.fetchval(
                """
                SELECT COALESCE(sum(estimated_amount),0)
                FROM cost_reservations
                WHERE operation_id = ANY($1::uuid[]) AND status='active'
                """,
                operation_ids,
            )
        )
        assert guarded_active == Decimal("0.30000000"), guarded_active
        assert await gateway.remaining_platform_daily_budget() == Decimal("0")

        # Policy disable is a fail-closed budget denial, not a provider call.
        await migration.execute(
            """
            UPDATE platform_provider_cost_guard
            SET enabled=false, updated_at=now(), version=version+1
            WHERE policy_key='platform'
            """
        )
        disabled_op = uuid4()
        operation_ids.append(disabled_op)
        await _insert_operation(
            migration,
            organization_id=ORG_ID,
            operation_id=disabled_op,
            suffix="disabled",
        )
        try:
            await gateway.reserve(_request(ORG_ID, disabled_op))
        except BudgetExceeded:
            pass
        else:
            raise AssertionError("disabled platform provider guard must fail closed")
        await migration.execute(
            """
            UPDATE platform_provider_cost_guard
            SET enabled=true, updated_at=now(), version=version+1
            WHERE policy_key='platform'
            """
        )

        # Provider accepted one reservation but actual cost exceeded the estimate.
        # The sunk fact must commit; all future reservations remain blocked.
        primary = handles[0]
        actual = ActualCost(
            context=primary.request.context,
            provider=primary.request.provider,
            model=primary.request.model,
            amount=Decimal("0.25"),
            currency="USD",
            confidence=CostConfidence.EXACT,
            pricing_snapshot_id="platform-guard-price-v1",
            external_provider_request_id="platform-guard-provider-request-1",
        )
        committed = await gateway.commit(primary, actual)
        assert committed.inserted is True
        stored = Decimal(
            await runtime.fetchval(
                "SELECT amount FROM cost_ledger WHERE id=$1",
                committed.entry_id,
            )
        )
        assert stored == Decimal("0.25000000"), stored

        post_overshoot_op = uuid4()
        operation_ids.append(post_overshoot_op)
        await _insert_operation(
            migration,
            organization_id=second_org,
            operation_id=post_overshoot_op,
            suffix="post-overshoot",
        )
        try:
            await gateway.reserve(_request(second_org, post_overshoot_op))
        except BudgetExceeded:
            pass
        else:
            raise AssertionError("post-overshoot provider reservation must be denied")

        # Runtime role can read but cannot alter the platform policy.
        try:
            await runtime.execute(
                """
                UPDATE platform_provider_cost_guard
                SET daily_cap_usd=999999 WHERE policy_key='platform'
                """
            )
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            raise AssertionError("runtime must not mutate platform provider cost policy")

        print("platform provider USD/day hard-stop PostgreSQL acceptance: PASS")
    finally:
        # Use the migration role for deterministic cleanup of immutable financial
        # fixtures created only by this acceptance run.
        if operation_ids:
            await migration.execute(
                "DELETE FROM usage_ledger WHERE operation_id = ANY($1::uuid[])",
                operation_ids,
            )
            await migration.execute(
                "DELETE FROM cost_reservations WHERE operation_id = ANY($1::uuid[])",
                operation_ids,
            )
            await migration.execute(
                "DELETE FROM cost_ledger WHERE operation_id = ANY($1::uuid[])",
                operation_ids,
            )
            await migration.execute(
                "DELETE FROM idempotency_operations WHERE id = ANY($1::uuid[])",
                operation_ids,
            )
        await migration.execute("DELETE FROM organizations WHERE id=$1", second_org)
        if original_policy is not None:
            await migration.execute(
                """
                UPDATE platform_provider_cost_guard
                SET daily_cap_usd=$1, enabled=$2, fail_closed=$3,
                    metadata_json=$4::jsonb, updated_at=now(), version=$5
                WHERE policy_key='platform'
                """,
                original_policy["daily_cap_usd"],
                original_policy["enabled"],
                original_policy["fail_closed"],
                original_policy["metadata_json"],
                original_policy["version"],
            )
        await runtime.close()
        await migration.close()


if __name__ == "__main__":
    asyncio.run(main_async())
