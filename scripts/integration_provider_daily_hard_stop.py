from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from lumi_api.costs import BudgetExceeded, PostgresModelCostAccounting
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
            $1,$2,$3,'final.provider_daily_hard_stop','new',$4,
            '{}'::jsonb,0,now(),now(),1
        )
        """,
        operation_id,
        organization_id,
        f"provider-daily-{suffix}-{operation_id}",
        "0" * 64,
    )


async def _reserve(
    accounting: PostgresModelCostAccounting,
    *,
    organization_id: UUID,
    operation_id: UUID,
    provider: str,
    amount: Decimal,
) -> str:
    return await accounting.reserve_provider_cost(
        organization_id=organization_id,
        operation_id=operation_id,
        project_id=None,
        task_id=None,
        agent_run_id=None,
        generation_id=None,
        provider=provider,
        model="hard-stop-acceptance-v1",
        estimated_amount_usd=amount,
        confidence="estimated",
        pricing_snapshot_id="hard-stop-acceptance-price-v1",
        reservation_key=f"model:{provider}:hard-stop-acceptance-v1",
    )


async def _configure_limit(
    migration: asyncpg.Connection,
    *,
    provider: str,
    amount: Decimal,
) -> None:
    await migration.execute(
        """
        INSERT INTO provider_daily_cost_limits (
            provider, amount_limit_usd, enabled, metadata_json,
            created_at, updated_at, version
        ) VALUES ($1,$2,true,'{"source":"acceptance"}'::jsonb,now(),now(),1)
        ON CONFLICT (provider) DO UPDATE
        SET amount_limit_usd=EXCLUDED.amount_limit_usd,
            enabled=true,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=now(),
            version=provider_daily_cost_limits.version+1
        """,
        provider,
        amount,
    )


async def _expect_budget_denied(awaitable: object, label: str) -> None:
    try:
        await awaitable  # type: ignore[misc]
    except BudgetExceeded:
        return
    raise AssertionError(f"{label} must fail closed with BudgetExceeded")


async def _cleanup(
    migration: asyncpg.Connection,
    *,
    operation_ids: list[UUID],
    providers: list[str],
    secondary_org_id: UUID,
) -> None:
    await migration.execute(
        """
        UPDATE platform_cost_controls
        SET provider_daily_hard_stop_enabled=false,
            updated_at=now(), version=version+1
        WHERE id=1
        """
    )
    if operation_ids:
        await migration.execute(
            "DELETE FROM usage_ledger WHERE operation_id = ANY($1::uuid[])",
            operation_ids,
        )
        await migration.execute(
            "DELETE FROM cost_reservations WHERE operation_id = ANY($1::uuid[])",
            operation_ids,
        )
        # Cost truth is immutable to the application. Acceptance cleanup runs as
        # the migration owner and temporarily disables only the immutable trigger
        # while deleting rows owned by this test run.
        await migration.execute(
            "ALTER TABLE cost_ledger DISABLE TRIGGER trg_cost_ledger_immutable"
        )
        try:
            await migration.execute(
                "DELETE FROM cost_ledger WHERE operation_id = ANY($1::uuid[])",
                operation_ids,
            )
        finally:
            await migration.execute(
                "ALTER TABLE cost_ledger ENABLE TRIGGER trg_cost_ledger_immutable"
            )
        await migration.execute(
            "DELETE FROM idempotency_operations WHERE id = ANY($1::uuid[])",
            operation_ids,
        )
    if providers:
        await migration.execute(
            "DELETE FROM provider_daily_cost_limits WHERE provider = ANY($1::varchar[])",
            providers,
        )
    await migration.execute(
        "DELETE FROM organizations WHERE id=$1",
        secondary_org_id,
    )


async def main_async() -> None:
    runtime_dsn = _dsn("DATABASE_URL")
    migration_dsn = _dsn("MIGRATION_DATABASE_URL")
    runtime = await asyncpg.connect(runtime_dsn)
    migration = await asyncpg.connect(migration_dsn)
    accounting = PostgresModelCostAccounting(runtime_dsn)

    run_suffix = uuid4().hex[:10]
    secondary_org_id = uuid4()
    providers = [
        f"accept-missing-{run_suffix}",
        f"accept-concurrent-{run_suffix}",
        f"accept-exact-{run_suffix}",
    ]
    missing_provider, concurrent_provider, exact_provider = providers
    operation_ids: list[UUID] = []

    try:
        await migration.execute(
            """
            INSERT INTO organizations (
                id, name, slug, status, plan, settings_json,
                created_at, updated_at, version
            ) VALUES (
                $1,'Provider Daily Acceptance',$2,'active','development',
                '{}'::jsonb,now(),now(),1
            )
            """,
            secondary_org_id,
            f"provider-daily-{run_suffix}",
        )

        await _configure_limit(
            migration,
            provider=concurrent_provider,
            amount=Decimal("0.30"),
        )
        await _configure_limit(
            migration,
            provider=exact_provider,
            amount=Decimal("0.30"),
        )
        await migration.execute(
            """
            UPDATE platform_cost_controls
            SET provider_daily_hard_stop_enabled=true,
                updated_at=now(), version=version+1
            WHERE id=1
            """
        )

        # Missing provider configuration fails closed after the platform policy is on.
        missing_op = uuid4()
        operation_ids.append(missing_op)
        await _insert_operation(
            migration,
            organization_id=ORG_ID,
            operation_id=missing_op,
            suffix="missing",
        )
        await _expect_budget_denied(
            _reserve(
                accounting,
                organization_id=ORG_ID,
                operation_id=missing_op,
                provider=missing_provider,
                amount=Decimal("0.01"),
            ),
            "missing provider limit",
        )

        # Four concurrent requests span two organizations. The cap is global, not
        # tenant-local: exactly three 0.10 reservations may fit under 0.30.
        concurrent_ops = [uuid4() for _ in range(4)]
        operation_ids.extend(concurrent_ops)
        concurrent_orgs = [ORG_ID, secondary_org_id, ORG_ID, secondary_org_id]
        for index, (operation_id, organization_id) in enumerate(
            zip(concurrent_ops, concurrent_orgs, strict=True)
        ):
            await _insert_operation(
                migration,
                organization_id=organization_id,
                operation_id=operation_id,
                suffix=f"concurrent-{index}",
            )

        async def attempt(index: int) -> str | None:
            try:
                return await _reserve(
                    accounting,
                    organization_id=concurrent_orgs[index],
                    operation_id=concurrent_ops[index],
                    provider=concurrent_provider,
                    amount=Decimal("0.10"),
                )
            except BudgetExceeded:
                return None

        concurrent_results = await asyncio.gather(*(attempt(i) for i in range(4)))
        concurrent_tickets = [item for item in concurrent_results if item is not None]
        assert len(concurrent_tickets) == 3, concurrent_results
        globally_reserved = Decimal(
            await migration.fetchval(
                """
                SELECT COALESCE(sum(estimated_amount),0)
                FROM cost_reservations
                WHERE provider=$1 AND budget_day_utc=(now() AT TIME ZONE 'UTC')::date
                  AND status='active' AND expires_at > now()
                """,
                concurrent_provider,
            )
        )
        assert globally_reserved == Decimal("0.30000000"), globally_reserved
        for ticket in concurrent_tickets:
            await accounting.release_provider_cost(
                reservation_ticket=ticket,
                reason="acceptance_release",
            )

        # Exact limit is allowed and idempotent replay returns the same reservation.
        exact_op = uuid4()
        operation_ids.append(exact_op)
        await _insert_operation(
            migration,
            organization_id=ORG_ID,
            operation_id=exact_op,
            suffix="exact",
        )
        exact_ticket = await _reserve(
            accounting,
            organization_id=ORG_ID,
            operation_id=exact_op,
            provider=exact_provider,
            amount=Decimal("0.30"),
        )
        replay_ticket = await _reserve(
            accounting,
            organization_id=ORG_ID,
            operation_id=exact_op,
            provider=exact_provider,
            amount=Decimal("0.30"),
        )
        assert replay_ticket == exact_ticket

        reservation_id = UUID(exact_ticket)
        original_day = await migration.fetchval(
            "SELECT budget_day_utc FROM cost_reservations WHERE id=$1",
            reservation_id,
        )
        await migration.execute(
            """
            UPDATE cost_reservations
            SET budget_day_utc=budget_day_utc-1
            WHERE id=$1
            """,
            reservation_id,
        )
        tamper_day = await migration.fetchval(
            "SELECT budget_day_utc FROM cost_reservations WHERE id=$1",
            reservation_id,
        )
        assert tamper_day == original_day

        overflow_op = uuid4()
        operation_ids.append(overflow_op)
        await _insert_operation(
            migration,
            organization_id=secondary_org_id,
            operation_id=overflow_op,
            suffix="overflow-active",
        )
        await _expect_budget_denied(
            _reserve(
                accounting,
                organization_id=secondary_org_id,
                operation_id=overflow_op,
                provider=exact_provider,
                amount=Decimal("0.00000001"),
            ),
            "exact-limit overflow",
        )

        # Provider-accepted actual cost may exceed the estimate. It is sunk cost and
        # must be recorded, then all subsequent admissions for that provider/day stop.
        await accounting.commit_provider_cost(
            reservation_ticket=exact_ticket,
            actual_amount_usd=Decimal("0.35"),
            confidence="exact",
            pricing_snapshot_id="hard-stop-acceptance-price-v1",
            provider_request_id=f"request-{run_suffix}",
            usage={},
        )
        ledger_row = await migration.fetchrow(
            """
            SELECT amount, budget_day_utc
            FROM cost_ledger
            WHERE operation_id=$1 AND entry_type='actual_cost'
            """,
            exact_op,
        )
        assert Decimal(ledger_row["amount"]) == Decimal("0.35000000")
        assert ledger_row["budget_day_utc"] == original_day

        post_actual_op = uuid4()
        operation_ids.append(post_actual_op)
        await _insert_operation(
            migration,
            organization_id=ORG_ID,
            operation_id=post_actual_op,
            suffix="post-actual",
        )
        await _expect_budget_denied(
            _reserve(
                accounting,
                organization_id=ORG_ID,
                operation_id=post_actual_op,
                provider=exact_provider,
                amount=Decimal("0.01"),
            ),
            "post-actual overspend",
        )

        # Runtime identity may observe policy but cannot mutate platform caps.
        try:
            await runtime.execute(
                """
                UPDATE platform_cost_controls
                SET provider_daily_hard_stop_enabled=false
                WHERE id=1
                """
            )
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            raise AssertionError("lumi_app must not mutate platform cost controls")
    finally:
        await _cleanup(
            migration,
            operation_ids=operation_ids,
            providers=providers,
            secondary_org_id=secondary_org_id,
        )
        await runtime.close()
        await migration.close()


def main() -> int:
    asyncio.run(main_async())
    print("Provider daily USD hard-stop PostgreSQL integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
