from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingImports]
from lumi_model_gateway.models import (
    CostConfidence as ModelCostConfidence,
    CostEstimate,
    ModelRequest,
    ModelUsage,
    RouteCandidate,
)
from lumi_model_gateway.ports import BudgetReservation, CostTelemetry

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


class Node27BudgetPort:
    """Durable NODE-27 implementation of the NODE-22 BudgetPort contract."""

    def __init__(self, gateway: PostgresCostGateway) -> None:
        self.gateway = gateway
        self._handles: dict[UUID, ReservationHandle] = {}

    async def reserve(
        self,
        request: ModelRequest,
        candidate: RouteCandidate,
    ) -> BudgetReservation:
        estimate = candidate.estimate
        amount = estimate.amount_usd or Decimal("0")
        reservation_request = BudgetReservationRequest(
            context=_context(request),
            provider=candidate.model.provider,
            model=candidate.model.model,
            estimated_amount=amount,
            pricing_snapshot_id=estimate.pricing_snapshot_id,
            confidence=_confidence(estimate.confidence),
            reservation_key=f"{candidate.model.provider}:{candidate.model.model}",
            metadata={
                "capability": request.capability.value,
                "registry_snapshot_id": candidate.model.registry_snapshot_id,
                "model_revision_id": candidate.model.model_revision_id,
                "estimate_unknown": estimate.amount_usd is None,
            },
        )
        try:
            handle = await self.gateway.reserve(reservation_request)
        except BudgetExceeded as exc:
            return BudgetReservation(False, reason=exc.code)
        self._handles[handle.reservation_id] = handle
        remaining = await self.gateway.remaining_budget(reservation_request)
        return BudgetReservation(
            True,
            reservation_ref=str(handle.reservation_id),
            remaining_usd=remaining,
        )

    async def settle(
        self,
        reservation: BudgetReservation,
        *,
        actual: CostEstimate,
        usage: ModelUsage,
        provider_request_id: str | None,
    ) -> None:
        handle = await self._handle(reservation)
        usage_facts = _usage_facts(usage)
        metadata: dict[str, Any] = {
            "amount_unknown": actual.amount_usd is None,
            "usage_fact_count": len(usage_facts),
        }
        await self.gateway.commit(
            handle,
            ActualCost(
                context=handle.request.context,
                provider=handle.request.provider,
                model=handle.request.model,
                amount=actual.amount_usd or Decimal("0"),
                currency=handle.request.currency,
                confidence=_confidence(actual.confidence),
                pricing_snapshot_id=actual.pricing_snapshot_id,
                external_provider_request_id=provider_request_id,
                usage=usage_facts,
                metadata=metadata,
            ),
        )
        self._handles.pop(handle.reservation_id, None)

    async def release(self, reservation: BudgetReservation) -> None:
        if not reservation.reservation_ref:
            return
        try:
            handle = await self._handle(reservation)
        except ValueError:
            return
        await self.gateway.release(handle, reason="provider_not_accepted")
        self._handles.pop(handle.reservation_id, None)

    async def _handle(self, reservation: BudgetReservation) -> ReservationHandle:
        if not reservation.reservation_ref:
            raise ValueError("COST_RESERVATION_REF_REQUIRED")
        try:
            reservation_id = UUID(reservation.reservation_ref)
        except ValueError as exc:
            raise ValueError("COST_RESERVATION_REF_INVALID") from exc
        cached = self._handles.get(reservation_id)
        if cached is not None:
            return cached
        recovered = await _load_reservation_handle(self.gateway.dsn, reservation_id)
        self._handles[reservation_id] = recovered
        return recovered


class Node27CostTelemetryPort:
    """Non-financial telemetry seam; settle() is the only provider-cost writer."""

    def __init__(self) -> None:
        self.records: list[CostTelemetry] = []

    async def record(self, telemetry: CostTelemetry) -> None:
        self.records.append(telemetry)


async def _load_reservation_handle(dsn: str, reservation_id: UUID) -> ReservationHandle:
    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow(
            "SELECT * FROM cost_reservations WHERE id=$1",
            reservation_id,
        )
    finally:
        await connection.close()
    if row is None:
        raise ValueError("COST_RESERVATION_NOT_FOUND")
    request = BudgetReservationRequest(
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
        metadata=dict(row["metadata_json"] or {}),
    )
    return ReservationHandle(
        reservation_id=reservation_id,
        request=request,
        replayed=True,
    )


def _context(request: ModelRequest) -> CostContext:
    return CostContext(
        organization_id=request.organization_id,
        operation_id=request.operation_id,
        project_id=request.project_id,
        task_id=request.task_id,
        agent_run_id=request.agent_run_id,
        generation_id=request.generation_id,
    )


def _confidence(value: ModelCostConfidence) -> CostConfidence:
    return CostConfidence(value.value)


def _usage_facts(usage: ModelUsage) -> tuple[UsageFact, ...]:
    values: list[UsageFact] = []
    if usage.input_tokens:
        values.append(UsageFact("llm.input_tokens", Decimal(usage.input_tokens), "tokens"))
    if usage.cached_input_tokens:
        values.append(
            UsageFact("llm.cached_input_tokens", Decimal(usage.cached_input_tokens), "tokens")
        )
    if usage.output_tokens:
        values.append(UsageFact("llm.output_tokens", Decimal(usage.output_tokens), "tokens"))
    if usage.images:
        values.append(UsageFact("image.generations", Decimal(usage.images), "images"))
    if usage.video_seconds:
        values.append(UsageFact("video.seconds", usage.video_seconds, "seconds"))
    values.append(UsageFact("provider.requests", Decimal(usage.requests), "requests"))
    return tuple(values)
