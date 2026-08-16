from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg  # pyright: ignore[reportMissingImports]

from .contracts import (
    ActualCost,
    BudgetExceeded,
    BudgetReservationRequest,
    BudgetScope,
    CostAdjustment,
    CostConfidence,
    CostContext,
    CostLedgerConflict,
    CostSummary,
    LedgerWriteResult,
    QuotaExceeded,
    QuotaLease,
    ReservationConflict,
    ReservationHandle,
    UsageFact,
    UsageSummary,
    lifetime_period_key,
    month_period_key,
)


class PostgresCostGateway:
    """Durable NODE-27 provider-cost, budget and quota gateway.

    Financial facts are append-only. Only reservation/quota occupancy rows mutate.
    The caller owns production connection-role/tenant composition.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = _asyncpg_dsn(dsn)

    async def reserve(
        self,
        request: BudgetReservationRequest,
    ) -> ReservationHandle:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await self._lock_budget_domain(
                    connection,
                    request.context.organization_id,
                )
                await self._expire_reservations(
                    connection,
                    request.context.organization_id,
                )
                existing = await connection.fetchrow(
                    """
                    SELECT * FROM cost_reservations
                    WHERE organization_id=$1
                      AND operation_id=$2
                      AND reservation_key=$3
                    FOR UPDATE
                    """,
                    request.context.organization_id,
                    request.context.operation_id,
                    request.key,
                )
                if existing is not None:
                    self._assert_reservation_identity(existing, request)
                    if existing["status"] in {"active", "committed"}:
                        return ReservationHandle(
                            reservation_id=existing["id"],
                            request=request,
                            replayed=True,
                        )
                    if existing["status"] not in {"released", "expired"}:
                        raise ReservationConflict(
                            "unsupported reservation state"
                        )
                    await self._check_budget_limits(
                        connection,
                        request=request,
                        projected_amount=request.estimated_amount,
                        exclude_reservation_id=existing["id"],
                    )
                    expires_at = datetime.now(UTC) + timedelta(
                        seconds=request.ttl_seconds
                    )
                    await connection.execute(
                        """
                        UPDATE cost_reservations
                        SET status='active', actual_amount=NULL, expires_at=$2,
                            committed_at=NULL, released_at=NULL,
                            release_reason=NULL, updated_at=now(), version=version+1
                        WHERE id=$1
                        """,
                        existing["id"],
                        expires_at,
                    )
                    return ReservationHandle(
                        reservation_id=existing["id"],
                        request=request,
                        replayed=False,
                    )

                await self._check_budget_limits(
                    connection,
                    request=request,
                    projected_amount=request.estimated_amount,
                    exclude_reservation_id=None,
                )
                reservation_id = uuid4()
                expires_at = datetime.now(UTC) + timedelta(
                    seconds=request.ttl_seconds
                )
                await connection.execute(
                    """
                    INSERT INTO cost_reservations (
                        id, organization_id, operation_id, project_id, task_id,
                        agent_run_id, generation_id, provider, model, reservation_key,
                        estimated_amount, currency, pricing_snapshot_id, confidence,
                        status, expires_at, metadata_json, created_at, updated_at, version
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                        'active',$15,$16::jsonb,now(),now(),1
                    )
                    """,
                    reservation_id,
                    request.context.organization_id,
                    request.context.operation_id,
                    request.context.project_id,
                    request.context.task_id,
                    request.context.agent_run_id,
                    request.context.generation_id,
                    request.provider,
                    request.model,
                    request.key,
                    request.estimated_amount,
                    request.currency,
                    request.pricing_snapshot_id,
                    request.confidence.value,
                    expires_at,
                    _json(request.metadata),
                )
                return ReservationHandle(
                    reservation_id=reservation_id,
                    request=request,
                    replayed=False,
                )
        finally:
            await connection.close()

    async def commit(
        self,
        handle: ReservationHandle,
        actual: ActualCost,
    ) -> LedgerWriteResult:
        """Atomically append Actual+Usage and settle its reservation."""
        self._assert_commit_context(handle, actual)
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await self._lock_budget_domain(
                    connection,
                    actual.context.organization_id,
                )
                reservation = await connection.fetchrow(
                    "SELECT * FROM cost_reservations WHERE id=$1 FOR UPDATE",
                    handle.reservation_id,
                )
                if reservation is None:
                    raise ReservationConflict("reservation not found")
                self._assert_reservation_identity(
                    reservation,
                    handle.request,
                )
                if reservation["status"] == "committed":
                    result = await self._existing_actual_result(
                        connection,
                        actual,
                    )
                    await self._assert_existing_usage(
                        connection,
                        actual,
                        result.entry_id,
                    )
                    return result
                if reservation["status"] == "released":
                    raise ReservationConflict(
                        "released not-accepted reservation cannot commit"
                    )
                if reservation["status"] not in {"active", "expired"}:
                    raise ReservationConflict(
                        "reservation cannot commit from "
                        f"{reservation['status']}"
                    )

                result = await self._insert_actual(connection, actual)
                await self._insert_usage_facts(
                    connection,
                    actual,
                    result.entry_id,
                )
                await connection.execute(
                    """
                    UPDATE cost_reservations
                    SET status='committed', actual_amount=$2, confidence=$3,
                        pricing_snapshot_id=$4, committed_at=now(),
                        released_at=NULL, release_reason=NULL,
                        updated_at=now(), version=version+1
                    WHERE id=$1
                    """,
                    handle.reservation_id,
                    actual.amount,
                    actual.confidence.value,
                    actual.pricing_snapshot_id,
                )
                return result
        finally:
            await connection.close()

    async def release(
        self,
        handle: ReservationHandle,
        *,
        reason: str,
    ) -> None:
        if not reason or len(reason) > 128:
            raise ValueError("COST_RELEASE_REASON_INVALID")
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await self._lock_budget_domain(
                    connection,
                    handle.request.context.organization_id,
                )
                reservation = await connection.fetchrow(
                    "SELECT * FROM cost_reservations WHERE id=$1 FOR UPDATE",
                    handle.reservation_id,
                )
                if reservation is None:
                    raise ReservationConflict("reservation not found")
                self._assert_reservation_identity(
                    reservation,
                    handle.request,
                )
                if reservation["status"] == "committed":
                    raise ReservationConflict(
                        "committed reservation cannot be released"
                    )
                if reservation["status"] == "released":
                    return
                await connection.execute(
                    """
                    UPDATE cost_reservations
                    SET status='released', released_at=now(), release_reason=$2,
                        updated_at=now(), version=version+1
                    WHERE id=$1
                    """,
                    handle.reservation_id,
                    reason,
                )
        finally:
            await connection.close()

    async def record_adjustment(
        self,
        adjustment: CostAdjustment,
    ) -> LedgerWriteResult:
        return await self._record_correction(
            adjustment,
            entry_type="adjustment",
        )

    async def record_reversal(
        self,
        *,
        context: CostContext,
        target_entry_id: UUID,
        reason: str,
        entry_key: str,
        occurred_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LedgerWriteResult:
        if not reason or len(reason) > 1000:
            raise ValueError("COST_REVERSAL_REASON_INVALID")
        if not entry_key or len(entry_key) > 128:
            raise ValueError("COST_ENTRY_KEY_INVALID")
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                target = await connection.fetchrow(
                    "SELECT * FROM cost_ledger WHERE id=$1",
                    target_entry_id,
                )
                if target is None:
                    raise CostLedgerConflict("reversal target not found")
                self._assert_correction_target(target, context)
                if target["entry_type"] not in {
                    "actual_cost",
                    "adjustment",
                }:
                    raise CostLedgerConflict(
                        "entry type cannot be reversed"
                    )
                return await self._insert_correction_row(
                    connection,
                    context=context,
                    target=target,
                    entry_type="reversal",
                    amount=-Decimal(target["amount"]),
                    reason=reason,
                    entry_key=entry_key,
                    confidence=CostConfidence.EXACT,
                    occurred_at=occurred_at or datetime.now(UTC),
                    metadata=metadata or {},
                )
        finally:
            await connection.close()

    async def summary(
        self,
        *,
        organization_id: UUID,
        from_time: datetime,
        to_time: datetime,
        project_id: UUID | None = None,
        currency: str = "USD",
    ) -> CostSummary:
        _validate_range(from_time, to_time)
        connection = await asyncpg.connect(self.dsn)
        try:
            args: list[Any] = [
                organization_id,
                from_time,
                to_time,
                currency,
            ]
            project_clause = ""
            if project_id is not None:
                args.append(project_id)
                project_clause = f" AND project_id=${len(args)}"
            row = await connection.fetchrow(
                f"""
                SELECT
                  COALESCE(sum(amount) FILTER (
                    WHERE entry_type='actual_cost'
                  ),0) AS actual_cost,
                  COALESCE(sum(amount) FILTER (
                    WHERE entry_type='adjustment'
                  ),0) AS adjustments,
                  COALESCE(sum(amount) FILTER (
                    WHERE entry_type='reversal'
                  ),0) AS reversals,
                  count(*) FILTER (
                    WHERE entry_type='actual_cost' AND confidence <> 'exact'
                  ) AS unknown_cost_entries
                FROM cost_ledger
                WHERE organization_id=$1
                  AND occurred_at >= $2 AND occurred_at < $3
                  AND currency=$4 AND cost_basis='provider_cost'
                  AND entry_type IN ('actual_cost','adjustment','reversal')
                  {project_clause}
                """,
                *args,
            )
            reservation_args: list[Any] = [organization_id, currency]
            reservation_project_clause = ""
            if project_id is not None:
                reservation_args.append(project_id)
                reservation_project_clause = (
                    f" AND project_id=${len(reservation_args)}"
                )
            active = await connection.fetchval(
                f"""
                SELECT COALESCE(sum(estimated_amount),0)
                FROM cost_reservations
                WHERE organization_id=$1 AND currency=$2
                  AND status='active' AND expires_at > now()
                  {reservation_project_clause}
                """,
                *reservation_args,
            )
        finally:
            await connection.close()
        actual_cost = Decimal(row["actual_cost"])
        adjustments = Decimal(row["adjustments"])
        reversals = Decimal(row["reversals"])
        return CostSummary(
            organization_id=organization_id,
            currency=currency,
            actual_cost=actual_cost,
            adjustments=adjustments,
            reversals=reversals,
            net_provider_cost=actual_cost + adjustments + reversals,
            active_reservations=Decimal(active),
            unknown_cost_entries=int(row["unknown_cost_entries"]),
            from_time=from_time,
            to_time=to_time,
            project_id=project_id,
        )

    async def usage_summary(
        self,
        *,
        organization_id: UUID,
        from_time: datetime,
        to_time: datetime,
        project_id: UUID | None = None,
    ) -> tuple[UsageSummary, ...]:
        _validate_range(from_time, to_time)
        connection = await asyncpg.connect(self.dsn)
        try:
            args: list[Any] = [organization_id, from_time, to_time]
            project_clause = ""
            if project_id is not None:
                args.append(project_id)
                project_clause = f" AND project_id=${len(args)}"
            rows = await connection.fetch(
                f"""
                SELECT metric, unit, sum(quantity) AS quantity
                FROM usage_ledger
                WHERE organization_id=$1
                  AND occurred_at >= $2 AND occurred_at < $3
                  {project_clause}
                GROUP BY metric, unit
                ORDER BY metric, unit
                """,
                *args,
            )
        finally:
            await connection.close()
        return tuple(
            UsageSummary(
                organization_id=organization_id,
                metric=row["metric"],
                quantity=Decimal(row["quantity"]),
                unit=row["unit"],
                from_time=from_time,
                to_time=to_time,
                project_id=project_id,
            )
            for row in rows
        )

    async def remaining_budget(
        self,
        request: BudgetReservationRequest,
    ) -> Decimal | None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await self._lock_budget_domain(
                    connection,
                    request.context.organization_id,
                )
                limits = await self._applicable_budget_limits(
                    connection,
                    request,
                )
                if not limits:
                    return None
                remainings: list[Decimal] = []
                for limit in limits:
                    spent = await self._scope_cost(
                        connection,
                        limit,
                        request,
                    )
                    active = await self._scope_active_reservations(
                        connection,
                        limit,
                        request,
                        exclude_reservation_id=None,
                    )
                    remainings.append(
                        Decimal(limit["amount_limit"])
                        + Decimal(limit["tolerance_amount"])
                        - spent
                        - active
                    )
                return min(remainings)
        finally:
            await connection.close()

    async def acquire_quota_lease(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        metric: str,
        quantity: Decimal,
        unit: str,
        ttl_seconds: int = 900,
        period_key: str = "lifetime",
    ) -> QuotaLease:
        if not isinstance(quantity, Decimal) or quantity <= 0:
            raise ValueError("QUOTA_LEASE_QUANTITY_INVALID")
        if not 5 <= ttl_seconds <= 86_400:
            raise ValueError("QUOTA_LEASE_TTL_INVALID")
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                    f"quota:{organization_id}:{metric}",
                )
                existing = await connection.fetchrow(
                    """
                    SELECT * FROM quota_leases
                    WHERE organization_id=$1
                      AND operation_id=$2
                      AND metric=$3
                    FOR UPDATE
                    """,
                    organization_id,
                    operation_id,
                    metric,
                )
                now = datetime.now(UTC)
                if (
                    existing is not None
                    and existing["released_at"] is None
                    and existing["expires_at"] > now
                ):
                    if (
                        Decimal(existing["quantity"]) != quantity
                        or existing["unit"] != unit
                    ):
                        raise ReservationConflict(
                            "quota lease replay mismatch"
                        )
                    return QuotaLease(
                        lease_id=existing["id"],
                        organization_id=organization_id,
                        operation_id=operation_id,
                        metric=metric,
                        quantity=quantity,
                        unit=unit,
                        expires_at=existing["expires_at"],
                        replayed=True,
                    )

                limit = await connection.fetchrow(
                    """
                    SELECT * FROM quota_limits
                    WHERE organization_id=$1
                      AND scope_type='organization'
                      AND scope_id IS NULL
                      AND metric=$2 AND period_key=$3 AND enabled
                    """,
                    organization_id,
                    metric,
                    period_key,
                )
                if limit is not None:
                    if limit["unit"] != unit:
                        raise QuotaExceeded("quota unit mismatch")
                    active = Decimal(
                        await connection.fetchval(
                            """
                            SELECT COALESCE(sum(quantity),0)
                            FROM quota_leases
                            WHERE organization_id=$1 AND metric=$2
                              AND released_at IS NULL
                              AND expires_at > now()
                              AND ($3::uuid IS NULL OR id <> $3)
                            """,
                            organization_id,
                            metric,
                            (
                                existing["id"]
                                if existing is not None
                                else None
                            ),
                        )
                    )
                    if active + quantity > Decimal(
                        limit["quantity_limit"]
                    ):
                        raise QuotaExceeded(
                            f"quota {metric} would exceed "
                            f"{limit['quantity_limit']} {unit}"
                        )

                lease_id = (
                    existing["id"] if existing is not None else uuid4()
                )
                expires_at = now + timedelta(seconds=ttl_seconds)
                if existing is None:
                    await connection.execute(
                        """
                        INSERT INTO quota_leases (
                            id, organization_id, operation_id, metric,
                            quantity, unit, expires_at, created_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,now())
                        """,
                        lease_id,
                        organization_id,
                        operation_id,
                        metric,
                        quantity,
                        unit,
                        expires_at,
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE quota_leases
                        SET quantity=$2, unit=$3, expires_at=$4,
                            released_at=NULL
                        WHERE id=$1
                        """,
                        lease_id,
                        quantity,
                        unit,
                        expires_at,
                    )
                return QuotaLease(
                    lease_id=lease_id,
                    organization_id=organization_id,
                    operation_id=operation_id,
                    metric=metric,
                    quantity=quantity,
                    unit=unit,
                    expires_at=expires_at,
                    replayed=False,
                )
        finally:
            await connection.close()

    async def release_quota_lease(
        self,
        lease: QuotaLease,
    ) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            await connection.execute(
                """
                UPDATE quota_leases
                SET released_at=COALESCE(released_at,now())
                WHERE id=$1 AND organization_id=$2
                """,
                lease.lease_id,
                lease.organization_id,
            )
        finally:
            await connection.close()

    async def _record_correction(
        self,
        adjustment: CostAdjustment,
        *,
        entry_type: str,
    ) -> LedgerWriteResult:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                target = await connection.fetchrow(
                    "SELECT * FROM cost_ledger WHERE id=$1",
                    adjustment.target_entry_id,
                )
                if target is None:
                    raise CostLedgerConflict(
                        "adjustment target not found"
                    )
                self._assert_correction_target(
                    target,
                    adjustment.context,
                )
                if target["entry_type"] != "actual_cost":
                    raise CostLedgerConflict(
                        "adjustment must target actual cost"
                    )
                return await self._insert_correction_row(
                    connection,
                    context=adjustment.context,
                    target=target,
                    entry_type=entry_type,
                    amount=adjustment.amount_delta,
                    reason=adjustment.reason,
                    entry_key=adjustment.entry_key,
                    confidence=adjustment.confidence,
                    occurred_at=adjustment.occurred_at,
                    metadata=adjustment.metadata,
                )
        finally:
            await connection.close()

    async def _insert_correction_row(
        self,
        connection: Any,
        *,
        context: CostContext,
        target: Any,
        entry_type: str,
        amount: Decimal,
        reason: str,
        entry_key: str,
        confidence: CostConfidence,
        occurred_at: datetime,
        metadata: dict[str, Any],
    ) -> LedgerWriteResult:
        entry_id = uuid4()
        payload = {
            **metadata,
            "reason": reason,
            "target_entry_id": str(target["id"]),
        }
        inserted = await connection.fetchrow(
            """
            INSERT INTO cost_ledger (
                id, organization_id, operation_id, project_id, task_id,
                agent_run_id, generation_id, reverses_entry_id, provider, model,
                entry_type, entry_key, amount, currency, pricing_snapshot_id,
                external_provider_request_id, confidence, cost_basis, source,
                occurred_at, metadata_json, created_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                $16,$17,'provider_cost','reconciliation',$18,$19::jsonb,now()
            )
            ON CONFLICT ON CONSTRAINT uq_cost_ledger_operation_entry_key
            DO NOTHING
            RETURNING id
            """,
            entry_id,
            context.organization_id,
            context.operation_id,
            context.project_id,
            context.task_id,
            context.agent_run_id,
            context.generation_id,
            target["id"],
            target["provider"],
            target["model"],
            entry_type,
            entry_key,
            amount,
            target["currency"],
            target["pricing_snapshot_id"],
            target["external_provider_request_id"],
            confidence.value,
            occurred_at,
            _json(payload),
        )
        if inserted is not None:
            return LedgerWriteResult(
                entry_id=inserted["id"],
                inserted=True,
            )
        existing = await connection.fetchrow(
            """
            SELECT id, amount, currency, reverses_entry_id
            FROM cost_ledger
            WHERE organization_id=$1 AND operation_id=$2
              AND entry_type=$3 AND entry_key=$4
            """,
            context.organization_id,
            context.operation_id,
            entry_type,
            entry_key,
        )
        if (
            existing is None
            or Decimal(existing["amount"]) != amount
            or existing["currency"] != target["currency"]
            or existing["reverses_entry_id"] != target["id"]
        ):
            raise CostLedgerConflict(
                "correction replay differs from immutable fact"
            )
        return LedgerWriteResult(
            entry_id=existing["id"],
            inserted=False,
        )

    async def _insert_actual(
        self,
        connection: Any,
        actual: ActualCost,
    ) -> LedgerWriteResult:
        entry_id = uuid4()
        inserted = await connection.fetchrow(
            """
            INSERT INTO cost_ledger (
                id, organization_id, operation_id, project_id, task_id,
                agent_run_id, generation_id, provider, model, entry_type,
                entry_key, amount, currency, pricing_snapshot_id,
                external_provider_request_id, confidence, cost_basis, source,
                occurred_at, metadata_json, created_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,'actual_cost',$10,$11,$12,$13,
                $14,$15,'provider_cost','model_gateway',$16,$17::jsonb,now()
            )
            ON CONFLICT ON CONSTRAINT uq_cost_ledger_operation_entry_key
            DO NOTHING
            RETURNING id
            """,
            entry_id,
            actual.context.organization_id,
            actual.context.operation_id,
            actual.context.project_id,
            actual.context.task_id,
            actual.context.agent_run_id,
            actual.context.generation_id,
            actual.provider,
            actual.model,
            actual.entry_key,
            actual.amount,
            actual.currency,
            actual.pricing_snapshot_id,
            actual.external_provider_request_id,
            actual.confidence.value,
            actual.occurred_at,
            _json(actual.metadata),
        )
        if inserted is not None:
            return LedgerWriteResult(
                entry_id=inserted["id"],
                inserted=True,
            )
        return await self._existing_actual_result(connection, actual)

    async def _existing_actual_result(
        self,
        connection: Any,
        actual: ActualCost,
    ) -> LedgerWriteResult:
        existing = await connection.fetchrow(
            """
            SELECT id, amount, currency, provider, model,
                   pricing_snapshot_id, external_provider_request_id, confidence
            FROM cost_ledger
            WHERE organization_id=$1 AND operation_id=$2
              AND entry_type='actual_cost' AND entry_key=$3
            """,
            actual.context.organization_id,
            actual.context.operation_id,
            actual.entry_key,
        )
        if existing is None:
            raise CostLedgerConflict(
                "actual cost conflict row disappeared"
            )
        if (
            Decimal(existing["amount"]) != actual.amount
            or existing["currency"] != actual.currency
            or existing["provider"] != actual.provider
            or existing["model"] != actual.model
            or existing["pricing_snapshot_id"]
            != actual.pricing_snapshot_id
            or existing["external_provider_request_id"]
            != actual.external_provider_request_id
            or existing["confidence"] != actual.confidence.value
        ):
            raise CostLedgerConflict(
                "actual replay differs from immutable financial fact"
            )
        return LedgerWriteResult(
            entry_id=existing["id"],
            inserted=False,
        )

    async def _insert_usage_facts(
        self,
        connection: Any,
        actual: ActualCost,
        cost_entry_id: UUID,
    ) -> None:
        for fact in actual.usage:
            inserted = await connection.fetchrow(
                """
                INSERT INTO usage_ledger (
                    id, organization_id, operation_id, cost_entry_id,
                    project_id, task_id, agent_run_id, generation_id,
                    provider, model, external_provider_request_id, metric,
                    entry_key, quantity, unit, occurred_at, metadata_json,
                    created_at
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                    $16,'{}'::jsonb,now()
                )
                ON CONFLICT ON CONSTRAINT
                    uq_usage_ledger_operation_metric_key
                DO NOTHING
                RETURNING id
                """,
                uuid4(),
                actual.context.organization_id,
                actual.context.operation_id,
                cost_entry_id,
                actual.context.project_id,
                actual.context.task_id,
                actual.context.agent_run_id,
                actual.context.generation_id,
                actual.provider,
                actual.model,
                actual.external_provider_request_id,
                fact.metric,
                fact.entry_key,
                fact.quantity,
                fact.unit,
                actual.occurred_at,
            )
            if inserted is None:
                await self._assert_usage_fact(
                    connection,
                    actual,
                    fact,
                    cost_entry_id,
                )

    async def _assert_existing_usage(
        self,
        connection: Any,
        actual: ActualCost,
        cost_entry_id: UUID,
    ) -> None:
        for fact in actual.usage:
            await self._assert_usage_fact(
                connection,
                actual,
                fact,
                cost_entry_id,
            )

    async def _assert_usage_fact(
        self,
        connection: Any,
        actual: ActualCost,
        fact: UsageFact,
        cost_entry_id: UUID,
    ) -> None:
        existing = await connection.fetchrow(
            """
            SELECT quantity, unit, cost_entry_id
            FROM usage_ledger
            WHERE organization_id=$1 AND operation_id=$2
              AND metric=$3 AND entry_key=$4
            """,
            actual.context.organization_id,
            actual.context.operation_id,
            fact.metric,
            fact.entry_key,
        )
        if (
            existing is None
            or Decimal(existing["quantity"]) != fact.quantity
            or existing["unit"] != fact.unit
            or existing["cost_entry_id"] != cost_entry_id
        ):
            raise CostLedgerConflict(
                "usage replay differs from immutable usage fact"
            )

    async def _check_budget_limits(
        self,
        connection: Any,
        *,
        request: BudgetReservationRequest,
        projected_amount: Decimal,
        exclude_reservation_id: UUID | None,
    ) -> None:
        limits = await self._applicable_budget_limits(
            connection,
            request,
        )
        for limit in limits:
            spent = await self._scope_cost(
                connection,
                limit,
                request,
            )
            active = await self._scope_active_reservations(
                connection,
                limit,
                request,
                exclude_reservation_id=exclude_reservation_id,
            )
            maximum = (
                Decimal(limit["amount_limit"])
                + Decimal(limit["tolerance_amount"])
            )
            if spent + active + projected_amount > maximum:
                raise BudgetExceeded(
                    "budget exceeded: "
                    f"scope={limit['scope_type']} "
                    f"period={limit['period_key']} "
                    f"spent={spent} active={active} "
                    f"requested={projected_amount} max={maximum}"
                )

    async def _applicable_budget_limits(
        self,
        connection: Any,
        request: BudgetReservationRequest,
    ) -> list[Any]:
        context = request.context
        periods = (
            lifetime_period_key(),
            month_period_key(datetime.now(UTC)),
        )
        rows = await connection.fetch(
            """
            SELECT * FROM cost_budget_limits
            WHERE organization_id=$1 AND enabled AND currency=$2
              AND period_key = ANY($3::varchar[])
              AND (
                    (scope_type='organization' AND scope_id IS NULL)
                 OR (scope_type='project' AND scope_id=$4)
                 OR (scope_type='agent_run' AND scope_id=$5)
                 OR (scope_type='task' AND scope_id=$6)
                 OR (scope_type='operation' AND scope_id=$7)
              )
            ORDER BY scope_type, period_key, id
            """,
            context.organization_id,
            request.currency,
            list(periods),
            context.project_id,
            context.agent_run_id,
            context.task_id,
            context.operation_id,
        )
        return list(rows)

    async def _scope_cost(
        self,
        connection: Any,
        limit: Any,
        request: BudgetReservationRequest,
    ) -> Decimal:
        scope_clause, scope_value = self._scope_clause(limit, request)
        args: list[Any] = [
            request.context.organization_id,
            request.currency,
        ]
        if scope_value is not None:
            args.append(scope_value)
            scope_clause = scope_clause.format(index=len(args))
        period_clause = ""
        if str(limit["period_key"]).startswith("month:"):
            start, end = _month_bounds(str(limit["period_key"]))
            args.extend([start, end])
            period_clause = (
                f" AND occurred_at >= ${len(args) - 1}"
                f" AND occurred_at < ${len(args)}"
            )
        value = await connection.fetchval(
            f"""
            SELECT COALESCE(sum(amount),0)
            FROM cost_ledger
            WHERE organization_id=$1 AND currency=$2
              AND cost_basis='provider_cost'
              AND entry_type IN ('actual_cost','adjustment','reversal')
              {scope_clause}{period_clause}
            """,
            *args,
        )
        return Decimal(value)

    async def _scope_active_reservations(
        self,
        connection: Any,
        limit: Any,
        request: BudgetReservationRequest,
        *,
        exclude_reservation_id: UUID | None,
    ) -> Decimal:
        scope_clause, scope_value = self._scope_clause(limit, request)
        args: list[Any] = [
            request.context.organization_id,
            request.currency,
        ]
        if scope_value is not None:
            args.append(scope_value)
            scope_clause = scope_clause.format(index=len(args))
        exclude_clause = ""
        if exclude_reservation_id is not None:
            args.append(exclude_reservation_id)
            exclude_clause = f" AND id <> ${len(args)}"
        value = await connection.fetchval(
            f"""
            SELECT COALESCE(sum(estimated_amount),0)
            FROM cost_reservations
            WHERE organization_id=$1 AND currency=$2
              AND status='active' AND expires_at > now()
              {scope_clause}{exclude_clause}
            """,
            *args,
        )
        return Decimal(value)

    def _scope_clause(
        self,
        limit: Any,
        request: BudgetReservationRequest,
    ) -> tuple[str, UUID | None]:
        scope = BudgetScope(limit["scope_type"])
        if scope is BudgetScope.ORGANIZATION:
            return "", None
        field, value = {
            BudgetScope.PROJECT: (
                "project_id",
                request.context.project_id,
            ),
            BudgetScope.AGENT_RUN: (
                "agent_run_id",
                request.context.agent_run_id,
            ),
            BudgetScope.TASK: (
                "task_id",
                request.context.task_id,
            ),
            BudgetScope.OPERATION: (
                "operation_id",
                request.context.operation_id,
            ),
        }[scope]
        if value is None or value != limit["scope_id"]:
            raise BudgetExceeded(
                "budget scope context mismatch"
            )
        return f" AND {field}=${{index}}", value

    async def _expire_reservations(
        self,
        connection: Any,
        organization_id: UUID,
    ) -> None:
        await connection.execute(
            """
            UPDATE cost_reservations
            SET status='expired', released_at=now(), release_reason='ttl',
                updated_at=now(), version=version+1
            WHERE organization_id=$1
              AND status='active' AND expires_at <= now()
            """,
            organization_id,
        )

    async def _lock_budget_domain(
        self,
        connection: Any,
        organization_id: UUID,
    ) -> None:
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
            f"cost-budget:{organization_id}",
        )

    def _assert_reservation_identity(
        self,
        row: Any,
        request: BudgetReservationRequest,
    ) -> None:
        if (
            row["organization_id"] != request.context.organization_id
            or row["operation_id"] != request.context.operation_id
            or row["provider"] != request.provider
            or row["model"] != request.model
            or Decimal(row["estimated_amount"])
            != request.estimated_amount
            or row["currency"] != request.currency
            or row["pricing_snapshot_id"]
            != request.pricing_snapshot_id
        ):
            raise ReservationConflict(
                "reservation replay differs from immutable intent"
            )

    def _assert_commit_context(
        self,
        handle: ReservationHandle,
        actual: ActualCost,
    ) -> None:
        request = handle.request
        if (
            actual.context != request.context
            or actual.provider != request.provider
            or actual.model != request.model
            or actual.currency != request.currency
        ):
            raise ReservationConflict(
                "actual cost does not match reservation identity"
            )

    def _assert_correction_target(
        self,
        row: Any,
        context: CostContext,
    ) -> None:
        if (
            row["organization_id"] != context.organization_id
            or row["operation_id"] != context.operation_id
        ):
            raise CostLedgerConflict(
                "correction target context mismatch"
            )


def _asyncpg_dsn(dsn: str) -> str:
    for prefix in (
        "postgresql+psycopg://",
        "postgresql+asyncpg://",
    ):
        if dsn.startswith(prefix):
            return "postgresql://" + dsn[len(prefix) :]
    return dsn


def _json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_range(
    from_time: datetime,
    to_time: datetime,
) -> None:
    if (
        from_time.tzinfo is None
        or to_time.tzinfo is None
        or from_time >= to_time
    ):
        raise ValueError("COST_TIME_RANGE_INVALID")


def _month_bounds(period_key: str) -> tuple[datetime, datetime]:
    _, value = period_key.split(":", 1)
    year, month = (
        int(part) for part in value.split("-", 1)
    )
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end
