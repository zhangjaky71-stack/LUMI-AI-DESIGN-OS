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
    CostAdjustment,
    CostConfidence,
    CostContext,
    PostgresCostGateway,
    QuotaExceeded,
    UsageFact,
)
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


async def _insert_operation(
    connection: asyncpg.Connection,
    operation_id: UUID,
    *,
    suffix: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO idempotency_operations (
            id, organization_id, idempotency_key, operation_type, status,
            request_hash, result_json, attempt_count, created_at, updated_at, version
        ) VALUES (
            $1,$2,$3,'node27.cost.acceptance','new',$4,'{}'::jsonb,0,now(),now(),1
        )
        """,
        operation_id,
        ORG_ID,
        f"node27-{suffix}-{operation_id}",
        "0" * 64,
    )


async def _cleanup(
    migration: asyncpg.Connection,
    operation_ids: list[UUID],
    budget_ids: list[UUID],
    quota_ids: list[UUID],
) -> None:
    if operation_ids:
        await migration.execute(
            "DELETE FROM quota_leases WHERE operation_id = ANY($1::uuid[])",
            operation_ids,
        )
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
    if budget_ids:
        await migration.execute(
            "DELETE FROM cost_budget_limits WHERE id = ANY($1::uuid[])",
            budget_ids,
        )
    if quota_ids:
        await migration.execute(
            "DELETE FROM quota_limits WHERE id = ANY($1::uuid[])",
            quota_ids,
        )


async def main_async() -> None:
    runtime_dsn = _dsn("DATABASE_URL")
    migration_dsn = _dsn("MIGRATION_DATABASE_URL")
    runtime = await asyncpg.connect(runtime_dsn)
    migration = await asyncpg.connect(migration_dsn)
    gateway = PostgresCostGateway(runtime_dsn)
    operation_ids: list[UUID] = []
    budget_ids: list[UUID] = []
    quota_ids: list[UUID] = []
    try:
        # Idempotent cleanup from any interrupted prior run uses no fixed operation IDs;
        # this run therefore owns only the UUIDs created below.
        task_id = await migration.fetchval(
            "SELECT id FROM tasks WHERE organization_id=$1 AND project_id=$2 ORDER BY created_at LIMIT 1",
            ORG_ID,
            PROJECT_A_ID,
        )
        assert task_id is not None

        # Hierarchy: org 2.00 -> project 1.00 -> task 0.60. The narrowest scope wins.
        for scope_type, scope_id, limit in (
            ("organization", None, Decimal("2.00")),
            ("project", PROJECT_A_ID, Decimal("1.00")),
            ("task", task_id, Decimal("0.60")),
        ):
            budget_id = uuid4()
            budget_ids.append(budget_id)
            await migration.execute(
                """
                INSERT INTO cost_budget_limits (
                    id, organization_id, scope_type, scope_id, period_key,
                    amount_limit, currency, tolerance_amount, enabled,
                    metadata_json, created_at, updated_at, version
                ) VALUES ($1,$2,$3,$4,'lifetime',$5,'USD',0,true,'{}'::jsonb,now(),now(),1)
                """,
                budget_id,
                ORG_ID,
                scope_type,
                scope_id,
                limit,
            )

        concurrent_ops = [uuid4() for _ in range(10)]
        operation_ids.extend(concurrent_ops)
        for index, operation_id in enumerate(concurrent_ops):
            await _insert_operation(migration, operation_id, suffix=f"concurrent-{index}")

        def request_for(operation_id: UUID) -> BudgetReservationRequest:
            return BudgetReservationRequest(
                context=CostContext(
                    organization_id=ORG_ID,
                    operation_id=operation_id,
                    project_id=PROJECT_A_ID,
                    task_id=task_id,
                ),
                provider="mock",
                model="mock-v1",
                estimated_amount=Decimal("0.10"),
                currency="USD",
                pricing_snapshot_id="mock-price-v1",
                confidence=CostConfidence.ESTIMATED,
                reservation_key="model:mock:mock-v1",
            )

        async def attempt_reserve(operation_id: UUID):
            try:
                return await gateway.reserve(request_for(operation_id))
            except BudgetExceeded:
                return None

        results = await asyncio.gather(*(attempt_reserve(item) for item in concurrent_ops))
        handles = [item for item in results if item is not None]
        assert len(handles) == 6, len(handles)
        active = Decimal(
            await runtime.fetchval(
                """
                SELECT COALESCE(sum(estimated_amount),0) FROM cost_reservations
                WHERE organization_id=$1 AND status='active' AND expires_at > now()
                """,
                ORG_ID,
            )
        )
        assert active == Decimal("0.60000000"), active

        # Release one reservation; the previously rejected operation can reserve exactly
        # the newly freed 0.10 without changing financial truth.
        released = handles.pop()
        await gateway.release(released, reason="provider_not_accepted")
        rejected_op = next(
            operation_id
            for operation_id, result in zip(concurrent_ops, results, strict=True)
            if result is None
        )
        replacement = await gateway.reserve(request_for(rejected_op))
        handles.append(replacement)

        # Actual overshoots estimate after the provider has accepted. It MUST be recorded,
        # even though it puts task spend+active above the 0.60 preflight budget.
        primary = handles[0]
        actual = ActualCost(
            context=primary.request.context,
            provider="mock",
            model="mock-v1",
            amount=Decimal("0.25"),
            currency="USD",
            confidence=CostConfidence.EXACT,
            pricing_snapshot_id="mock-price-v1",
            external_provider_request_id="mock-request-1",
            usage=(
                UsageFact("input_tokens", Decimal("100"), "tokens"),
                UsageFact("output_tokens", Decimal("40"), "tokens"),
            ),
        )
        first_actual = await gateway.commit(primary, actual)
        assert first_actual.inserted is True
        replay_actual = await gateway.commit(primary, actual)
        assert replay_actual.entry_id == first_actual.entry_id
        assert replay_actual.inserted is False
        count_actual = await runtime.fetchval(
            """
            SELECT count(*) FROM cost_ledger
            WHERE operation_id=$1 AND entry_type='actual_cost'
            """,
            primary.request.context.operation_id,
        )
        assert int(count_actual) == 1

        historical = await runtime.fetchrow(
            """
            SELECT amount, pricing_snapshot_id, external_provider_request_id, confidence
            FROM cost_ledger WHERE id=$1
            """,
            first_actual.entry_id,
        )
        assert Decimal(historical["amount"]) == Decimal("0.25000000")
        assert historical["pricing_snapshot_id"] == "mock-price-v1"
        assert historical["external_provider_request_id"] == "mock-request-1"
        assert historical["confidence"] == "exact"

        # Existing active reservations + the 0.25 actual now exceed the task budget.
        # New spend is blocked, while the sunk actual above remains immutable.
        blocked_op = uuid4()
        operation_ids.append(blocked_op)
        await _insert_operation(migration, blocked_op, suffix="post-overshoot")
        try:
            await gateway.reserve(request_for(blocked_op))
        except BudgetExceeded:
            pass
        else:
            raise AssertionError("post-overshoot reservation must be denied")

        # Reconciliation is append-only: adjustment and reversal do not mutate actual row.
        adjustment = await gateway.record_adjustment(
            CostAdjustment(
                context=primary.request.context,
                target_entry_id=first_actual.entry_id,
                amount_delta=Decimal("0.05"),
                reason="provider invoice reconciliation",
                entry_key="invoice-v1",
                confidence=CostConfidence.EXACT,
            )
        )
        reversal = await gateway.record_reversal(
            context=primary.request.context,
            target_entry_id=adjustment.entry_id,
            reason="invoice correction withdrawn",
            entry_key="invoice-v1-reversal",
        )
        assert adjustment.entry_id != first_actual.entry_id
        assert reversal.entry_id != first_actual.entry_id
        unchanged = await runtime.fetchval(
            "SELECT amount FROM cost_ledger WHERE id=$1",
            first_actual.entry_id,
        )
        assert Decimal(unchanged) == Decimal("0.25000000")

        now = datetime.now(UTC)
        summary = await gateway.summary(
            organization_id=ORG_ID,
            project_id=PROJECT_A_ID,
            from_time=now - timedelta(hours=1),
            to_time=now + timedelta(hours=1),
        )
        assert summary.actual_cost >= Decimal("0.25")
        assert summary.adjustments >= Decimal("0.05")
        assert summary.reversals <= Decimal("-0.05")
        usage = await gateway.usage_summary(
            organization_id=ORG_ID,
            project_id=PROJECT_A_ID,
            from_time=now - timedelta(hours=1),
            to_time=now + timedelta(hours=1),
        )
        by_metric = {(item.metric, item.unit): item.quantity for item in usage}
        assert by_metric[("input_tokens", "tokens")] >= Decimal("100")
        assert by_metric[("output_tokens", "tokens")] >= Decimal("40")

        # Per-operation lower budget overrides all parent scopes.
        operation_limit_op = uuid4()
        operation_ids.append(operation_limit_op)
        await _insert_operation(migration, operation_limit_op, suffix="operation-limit")
        operation_budget_id = uuid4()
        budget_ids.append(operation_budget_id)
        await migration.execute(
            """
            INSERT INTO cost_budget_limits (
                id, organization_id, scope_type, scope_id, period_key,
                amount_limit, currency, tolerance_amount, enabled,
                metadata_json, created_at, updated_at, version
            ) VALUES ($1,$2,'operation',$3,'lifetime',0.05,'USD',0,true,'{}'::jsonb,now(),now(),1)
            """,
            operation_budget_id,
            ORG_ID,
            operation_limit_op,
        )
        try:
            await gateway.reserve(request_for(operation_limit_op))
        except BudgetExceeded:
            pass
        else:
            raise AssertionError("operation budget must be narrower than parent budget")

        # Concurrent-generation quota lease: only two live leases may coexist.
        quota_id = uuid4()
        quota_ids.append(quota_id)
        await migration.execute(
            """
            INSERT INTO quota_limits (
                id, organization_id, scope_type, scope_id, metric, period_key,
                quantity_limit, unit, enabled, metadata_json, created_at, updated_at, version
            ) VALUES (
                $1,$2,'organization',NULL,'concurrent_generations','lifetime',2,'generations',
                true,'{}'::jsonb,now(),now(),1
            )
            """,
            quota_id,
            ORG_ID,
        )
        quota_ops = [uuid4(), uuid4(), uuid4()]
        operation_ids.extend(quota_ops)
        for index, operation_id in enumerate(quota_ops):
            await _insert_operation(migration, operation_id, suffix=f"quota-{index}")
        first_lease = await gateway.acquire_quota_lease(
            organization_id=ORG_ID,
            operation_id=quota_ops[0],
            metric="concurrent_generations",
            quantity=Decimal("1"),
            unit="generations",
        )
        second_lease = await gateway.acquire_quota_lease(
            organization_id=ORG_ID,
            operation_id=quota_ops[1],
            metric="concurrent_generations",
            quantity=Decimal("1"),
            unit="generations",
        )
        assert first_lease.replayed is False and second_lease.replayed is False
        try:
            await gateway.acquire_quota_lease(
                organization_id=ORG_ID,
                operation_id=quota_ops[2],
                metric="concurrent_generations",
                quantity=Decimal("1"),
                unit="generations",
            )
        except QuotaExceeded:
            pass
        else:
            raise AssertionError("concurrent generation quota must reject third lease")
        await gateway.release_quota_lease(first_lease)
        third_lease = await gateway.acquire_quota_lease(
            organization_id=ORG_ID,
            operation_id=quota_ops[2],
            metric="concurrent_generations",
            quantity=Decimal("1"),
            unit="generations",
        )
        assert third_lease.replayed is False

        storage_quota_id = uuid4()
        quota_ids.append(storage_quota_id)
        await migration.execute(
            """
            INSERT INTO quota_limits (
                id, organization_id, scope_type, scope_id, metric, period_key,
                quantity_limit, unit, enabled, metadata_json, created_at, updated_at, version
            ) VALUES (
                $1,$2,'organization',NULL,'asset_storage_bytes','lifetime',1000,'bytes',
                true,'{}'::jsonb,now(),now(),1
            )
            """,
            storage_quota_id,
            ORG_ID,
        )
        await gateway.check_quantity_quota(
            organization_id=ORG_ID,
            metric="asset_storage_bytes",
            current_quantity=Decimal("900"),
            requested_delta=Decimal("100"),
            unit="bytes",
        )
        try:
            await gateway.check_quantity_quota(
                organization_id=ORG_ID,
                metric="asset_storage_bytes",
                current_quantity=Decimal("900"),
                requested_delta=Decimal("101"),
                unit="bytes",
            )
        except QuotaExceeded:
            pass
        else:
            raise AssertionError("asset storage quota hook must fail closed")

        # Runtime can append facts but cannot mutate/delete immutable cost truth or policy.
        for statement, args in (
            ("UPDATE cost_ledger SET amount=999 WHERE id=$1", (first_actual.entry_id,)),
            ("DELETE FROM cost_ledger WHERE id=$1", (first_actual.entry_id,)),
            (
                "UPDATE cost_budget_limits SET amount_limit=999 WHERE id=$1",
                (budget_ids[0],),
            ),
            (
                "UPDATE quota_limits SET quantity_limit=999 WHERE id=$1",
                (quota_id,),
            ),
        ):
            try:
                await runtime.execute(statement, *args)
            except asyncpg.InsufficientPrivilegeError:
                pass
            else:
                raise AssertionError(f"runtime mutation must be denied: {statement}")
    finally:
        await _cleanup(migration, operation_ids, budget_ids, quota_ids)
        await runtime.close()
        await migration.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-27 PostgreSQL cost ledger/budget/quota integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
