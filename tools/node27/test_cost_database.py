from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
from uuid import UUID

from lumi_api.costs import (
    ActualCost,
    BudgetExceeded,
    BudgetReservationRequest,
    CostAdjustment,
    CostConfidence,
    CostContext,
    CostLedgerConflict,
    QuotaExceeded,
    UsageFact,
)
from lumi_api.costs.gateway import PostgresCostGateway
from lumi_api.costs.read_service import PostgresCostReadService
from lumi_model_gateway.models import (
    Capability,
    CostConfidence as ModelCostConfidence,
    CostEstimate,
    HealthSnapshot,
    InputKind,
    ModelInput,
    ModelRequest,
    ProviderModel,
    RouteCandidate,
)
from lumi_api.costs.model_gateway_adapter import Node27BudgetPort

from seed_cost_baseline import COST_BASELINE, OP_BASELINE, ORG_A, ORG_B

OP_ONE = UUID("00000000-0000-7000-8000-000000002712")
OP_TWO = UUID("00000000-0000-7000-8000-000000002713")
OP_THREE = UUID("00000000-0000-7000-8000-000000002714")
OP_FOUR = UUID("00000000-0000-7000-8000-000000002715")
BUDGET_ID = UUID("00000000-0000-7000-8000-000000002731")
QUOTA_ID = UUID("00000000-0000-7000-8000-000000002732")


async def _insert_operation(connection, operation_id: UUID, key: str) -> None:
    await connection.execute(
        """
        INSERT INTO idempotency_operations (
            id, organization_id, idempotency_key, operation_type,
            request_hash, status, side_effect_kind, compensation_mode, paid
        ) VALUES ($1,$2,$3,'model.invoke',$4,'in_progress',
                  'paid_model_invocation','non_compensatable',true)
        ON CONFLICT (id) DO NOTHING
        """,
        operation_id,
        ORG_A,
        key,
        (key.encode("utf-8").hex() + "0" * 64)[:64],
    )


async def _setup_controls(dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            for op_id, key in (
                (OP_ONE, "node27-one"),
                (OP_TWO, "node27-two"),
                (OP_THREE, "node27-three"),
                (OP_FOUR, "node27-four"),
            ):
                await _insert_operation(connection, op_id, key)
            await connection.execute(
                """
                INSERT INTO cost_budget_limits (
                    id, organization_id, scope_type, scope_id, period_key,
                    amount_limit, currency, tolerance_amount, enforcement_mode, enabled
                ) VALUES ($1,$2,'organization',NULL,'lifetime',$3,'USD',0,'hard',true)
                ON CONFLICT DO NOTHING
                """,
                BUDGET_ID,
                ORG_A,
                Decimal("1.00000000"),
            )
            await connection.execute(
                """
                INSERT INTO quota_limits (
                    id, organization_id, scope_type, scope_id, metric, period_key,
                    quantity_limit, unit, enabled
                ) VALUES ($1,$2,'organization',NULL,'image.generations','lifetime',1,
                          'images',true)
                ON CONFLICT DO NOTHING
                """,
                QUOTA_ID,
                ORG_A,
            )
    finally:
        await connection.close()


async def _verify_migrated_baseline(dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow(
            "SELECT * FROM cost_ledger WHERE id=$1", COST_BASELINE
        )
    finally:
        await connection.close()
    assert row is not None
    assert row["organization_id"] == ORG_A
    assert row["operation_id"] == OP_BASELINE
    assert row["entry_type"] == "actual_cost"
    assert Decimal(row["amount"]) == Decimal("0.12500000")
    assert row["confidence"] == "unknown"
    assert row["status"] == "unknown"
    assert row["source"] == "legacy_migration"


async def _budget_and_ledger_invariants(dsn: str) -> UUID:
    gateway = PostgresCostGateway(dsn)
    request_one = BudgetReservationRequest(
        context=CostContext(organization_id=ORG_A, operation_id=OP_ONE),
        provider="fixture",
        model="model-a",
        estimated_amount=Decimal("0.75000000"),
        pricing_snapshot_id="pricing-node27",
        confidence=CostConfidence.ESTIMATED,
    )
    request_two = BudgetReservationRequest(
        context=CostContext(organization_id=ORG_A, operation_id=OP_TWO),
        provider="fixture",
        model="model-a",
        estimated_amount=Decimal("0.75000000"),
        pricing_snapshot_id="pricing-node27",
        confidence=CostConfidence.ESTIMATED,
    )

    async def attempt(request):
        try:
            return await gateway.reserve(request)
        except BudgetExceeded:
            return None

    first, second = await asyncio.gather(attempt(request_one), attempt(request_two))
    winners = [item for item in (first, second) if item is not None]
    assert len(winners) == 1, "concurrent reservations must not oversell budget"
    handle = winners[0]
    winning_operation = handle.request.context.operation_id

    actual = ActualCost(
        context=handle.request.context,
        provider=handle.request.provider,
        model=handle.request.model,
        amount=Decimal("0.70000000"),
        confidence=CostConfidence.EXACT,
        pricing_snapshot_id="pricing-node27",
        external_provider_request_id="provider-node27-1",
        usage=(
            UsageFact("llm.input_tokens", Decimal("100"), "tokens"),
            UsageFact("llm.output_tokens", Decimal("25"), "tokens"),
            UsageFact("provider.requests", Decimal("1"), "requests"),
        ),
    )
    inserted = await gateway.commit(handle, actual)
    assert inserted.inserted
    replay = await gateway.commit(handle, actual)
    assert replay.entry_id == inserted.entry_id
    assert replay.inserted is False

    conflicting = ActualCost(
        context=actual.context,
        provider=actual.provider,
        model=actual.model,
        amount=Decimal("0.71000000"),
        confidence=actual.confidence,
        pricing_snapshot_id=actual.pricing_snapshot_id,
        external_provider_request_id=actual.external_provider_request_id,
        usage=actual.usage,
    )
    try:
        await gateway.commit(handle, conflicting)
    except CostLedgerConflict:
        pass
    else:
        raise AssertionError("conflicting replay must fail")

    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        ledger_count = await connection.fetchval(
            """
            SELECT count(*) FROM cost_ledger
            WHERE organization_id=$1 AND operation_id=$2 AND entry_type='actual_cost'
            """,
            ORG_A,
            winning_operation,
        )
        usage_count = await connection.fetchval(
            "SELECT count(*) FROM usage_ledger WHERE operation_id=$1",
            winning_operation,
        )
        reservation_status = await connection.fetchval(
            "SELECT status FROM cost_reservations WHERE id=$1",
            handle.reservation_id,
        )
    finally:
        await connection.close()
    assert ledger_count == 1
    assert usage_count == 3
    assert reservation_status == "committed"

    adjustment = await gateway.record_adjustment(
        CostAdjustment(
            context=actual.context,
            target_entry_id=inserted.entry_id,
            amount_delta=Decimal("0.05000000"),
            reason="provider reconciliation fixture",
            entry_key="reconcile-1",
        )
    )
    assert adjustment.inserted
    reversal = await gateway.record_reversal(
        context=actual.context,
        target_entry_id=inserted.entry_id,
        reason="provider refund fixture",
        entry_key="refund-1",
    )
    assert reversal.inserted
    return inserted.entry_id


async def _immutability(dsn: str, target_entry_id: UUID) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        try:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE cost_ledger SET amount=999 WHERE id=$1", target_entry_id
                )
        except asyncpg.PostgresError:
            pass
        else:
            raise AssertionError("cost ledger UPDATE must be rejected")

        try:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM usage_ledger WHERE cost_entry_id=$1", target_entry_id
                )
        except asyncpg.PostgresError:
            pass
        else:
            raise AssertionError("usage ledger DELETE must be rejected")
    finally:
        await connection.close()


async def _quota_invariants(dsn: str) -> None:
    gateway = PostgresCostGateway(dsn)
    first = await gateway.acquire_quota_lease(
        organization_id=ORG_A,
        operation_id=OP_THREE,
        metric="image.generations",
        quantity=Decimal("1"),
        unit="images",
    )
    try:
        await gateway.acquire_quota_lease(
            organization_id=ORG_A,
            operation_id=OP_FOUR,
            metric="image.generations",
            quantity=Decimal("1"),
            unit="images",
        )
    except QuotaExceeded:
        pass
    else:
        raise AssertionError("quota oversubscription must fail")
    await gateway.release_quota_lease(first)
    second = await gateway.acquire_quota_lease(
        organization_id=ORG_A,
        operation_id=OP_FOUR,
        metric="image.generations",
        quantity=Decimal("1"),
        unit="images",
    )
    assert second.replayed is False


async def _unknown_cost_budget_fails_closed(dsn: str) -> None:
    port = Node27BudgetPort(PostgresCostGateway(dsn))
    request = ModelRequest(
        request_id=UUID("00000000-0000-7000-8000-000000002741"),
        organization_id=ORG_A,
        operation_id=OP_TWO,
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind=InputKind.TEXT, text="unknown cost"),),
    )
    model = ProviderModel(
        provider="fixture",
        model="unknown-price-model",
        capabilities=frozenset({Capability.LLM_REASONING}),
        paid=True,
    )
    candidate = RouteCandidate(
        model=model,
        estimate=CostEstimate(None, ModelCostConfidence.UNKNOWN),
        health=HealthSnapshot(),
        score=1,
        reason_codes=(),
    )
    reservation = await port.reserve(request, candidate)
    assert reservation.allowed is False
    assert reservation.reason == "COST_UNKNOWN_COST_HARD_BUDGET"


async def _rls_and_read_projection(app_dsn: str) -> None:
    import asyncpg

    service = PostgresCostReadService(app_dsn)
    summary_a = await service.summary(
        organization_id=ORG_A,
        from_time=__import__("datetime").datetime(2020, 1, 1, tzinfo=__import__("datetime").UTC),
        to_time=__import__("datetime").datetime(2030, 1, 1, tzinfo=__import__("datetime").UTC),
    )
    summary_b = await service.summary(
        organization_id=ORG_B,
        from_time=__import__("datetime").datetime(2020, 1, 1, tzinfo=__import__("datetime").UTC),
        to_time=__import__("datetime").datetime(2030, 1, 1, tzinfo=__import__("datetime").UTC),
    )
    assert summary_a["actual_cost"] > Decimal("0")
    assert summary_b["actual_cost"] == Decimal("0")

    connection = await asyncpg.connect(app_dsn)
    try:
        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.current_organization_id',$1,true)", str(ORG_A)
            )
            visible = await connection.fetchval("SELECT count(*) FROM cost_ledger")
            assert visible > 0
        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.current_organization_id',$1,true)", str(ORG_B)
            )
            hidden = await connection.fetchval("SELECT count(*) FROM cost_ledger")
            assert hidden == 0
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.current_organization_id',$1,true)", str(ORG_A)
                )
                await connection.execute(
                    "UPDATE cost_ledger SET amount=amount WHERE organization_id=$1",
                    ORG_A,
                )
        except asyncpg.PostgresError:
            pass
        else:
            raise AssertionError("lumi_app must not UPDATE cost_ledger")
    finally:
        await connection.close()


async def run(migration_dsn: str, app_dsn: str) -> None:
    await _verify_migrated_baseline(migration_dsn)
    await _setup_controls(migration_dsn)
    target = await _budget_and_ledger_invariants(migration_dsn)
    await _immutability(migration_dsn, target)
    await _quota_invariants(migration_dsn)
    await _unknown_cost_budget_fails_closed(migration_dsn)
    await _rls_and_read_projection(app_dsn)
    print("NODE-27 Cost Ledger PostgreSQL invariants: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration-dsn", required=True)
    parser.add_argument("--app-dsn", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.migration_dsn, args.app_dsn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
