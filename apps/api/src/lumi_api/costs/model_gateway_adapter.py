from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from .contracts import (
    ActualCost,
    BudgetExceeded,
    BudgetReservationRequest,
    CostConfidence,
    CostContext,
    ReservationHandle,
    UsageFact,
)
from .gateway import PostgresCostGateway


_PROVIDER_DAILY_HARD_STOP_MARKERS = (
    "COST_PROVIDER_DAILY_BUDGET_EXCEEDED",
    "COST_PROVIDER_DAILY_CURRENCY_UNSUPPORTED",
    "COST_PROVIDER_DAILY_LIMIT_NOT_CONFIGURED",
    "COST_PROVIDER_DAILY_PROVIDER_REQUIRED",
    "COST_PROVIDER_DAILY_RESERVATION_REQUIRED",
)


class PostgresModelCostAccounting:
    """Structural implementation of Model Gateway's DB-neutral CostAccountingPort.

    This module intentionally does not import ``lumi_model_gateway``. Composition code can
    pass an instance to ``LedgerBudgetGuard`` by Protocol compatibility.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.gateway = PostgresCostGateway(dsn)

    async def reserve_provider_cost(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        project_id: UUID | None,
        task_id: UUID | None,
        agent_run_id: UUID | None,
        generation_id: UUID | None,
        provider: str,
        model: str,
        estimated_amount_usd: Decimal,
        confidence: str,
        pricing_snapshot_id: str | None,
        reservation_key: str,
    ) -> str:
        request = BudgetReservationRequest(
            context=CostContext(
                organization_id=organization_id,
                operation_id=operation_id,
                project_id=project_id,
                task_id=task_id,
                agent_run_id=agent_run_id,
                generation_id=generation_id,
            ),
            provider=provider,
            model=model,
            estimated_amount=estimated_amount_usd,
            currency="USD",
            pricing_snapshot_id=pricing_snapshot_id,
            confidence=CostConfidence(confidence),
            reservation_key=reservation_key,
            metadata={"source": "model_gateway"},
        )
        try:
            handle = await self.gateway.reserve(request)
        except asyncpg.PostgresError as exc:
            _raise_provider_daily_budget_error(exc)
            raise
        return str(handle.reservation_id)

    async def commit_provider_cost(
        self,
        *,
        reservation_ticket: str,
        actual_amount_usd: Decimal,
        confidence: str,
        pricing_snapshot_id: str | None,
        provider_request_id: str | None,
        usage: dict[str, tuple[Decimal, str]],
    ) -> None:
        handle = await self._load_handle(reservation_ticket)
        facts = tuple(
            UsageFact(metric=metric, quantity=quantity, unit=unit)
            for metric, (quantity, unit) in sorted(usage.items())
        )
        actual = ActualCost(
            context=handle.request.context,
            provider=handle.request.provider,
            model=handle.request.model,
            amount=actual_amount_usd,
            currency="USD",
            confidence=CostConfidence(confidence),
            pricing_snapshot_id=pricing_snapshot_id,
            external_provider_request_id=provider_request_id,
            usage=facts,
            metadata={"source": "model_gateway"},
        )
        await self.gateway.commit(handle, actual)

    async def release_provider_cost(
        self,
        *,
        reservation_ticket: str,
        reason: str,
    ) -> None:
        handle = await self._load_handle(reservation_ticket)
        await self.gateway.release(handle, reason=reason)

    async def _load_handle(self, reservation_ticket: str) -> ReservationHandle:
        try:
            reservation_id = UUID(reservation_ticket)
        except ValueError as exc:
            raise ValueError("COST_RESERVATION_TICKET_INVALID") from exc
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                "SELECT * FROM cost_reservations WHERE id=$1",
                reservation_id,
            )
        finally:
            await connection.close()
        if row is None:
            raise RuntimeError("COST_RESERVATION_NOT_FOUND")
        request = _request_from_row(row)
        return ReservationHandle(
            reservation_id=reservation_id,
            request=request,
            replayed=row["status"] == "committed",
        )


def _raise_provider_daily_budget_error(exc: asyncpg.PostgresError) -> None:
    message = str(exc)
    if any(marker in message for marker in _PROVIDER_DAILY_HARD_STOP_MARKERS):
        raise BudgetExceeded(message) from exc


def _request_from_row(row: asyncpg.Record) -> BudgetReservationRequest:
    metadata: dict[str, Any] = dict(row["metadata_json"] or {})
    return BudgetReservationRequest(
        context=CostContext(
            organization_id=row["organization_id"],
            operation_id=row["operation_id"],
            project_id=row["project_id"],
            task_id=row["task_id"],
            agent_run_id=row["agent_run_id"],
            generation_id=row["generation_id"],
        ),
        provider=row["provider"],
        model=row["model"],
        estimated_amount=Decimal(row["estimated_amount"]),
        currency=row["currency"],
        pricing_snapshot_id=row["pricing_snapshot_id"],
        confidence=CostConfidence(row["confidence"]),
        reservation_key=row["reservation_key"],
        metadata=metadata,
    )
