from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from lumi_api.costs.contracts import (
    BudgetReservationRequest,
    CostConfidence,
    CostContext,
    ReservationHandle,
)
from lumi_api.costs.gateway import PostgresCostGateway
from lumi_auto_repair import (
    AutoRepairJob,
    BudgetReservation,
    RepairCandidate,
    RepairCostEstimate,
    RepairPlan,
)


class Node27RepairBudgetAdapter:
    """Reserve a loop-level NODE-27 budget envelope without double actual cost.

    Paid media execution (NODE-47/NODE-46 through Model Gateway) already records
    the authoritative provider ActualCost. NODE-51 reserves capacity before the
    call, then releases that envelope once downstream settlement evidence exists.
    """

    def __init__(self, gateway: PostgresCostGateway) -> None:
        self.gateway = gateway

    async def reserve(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        estimate: RepairCostEstimate,
    ) -> BudgetReservation:
        request = self._request(
            job=job,
            iteration=plan.iteration,
            estimate=estimate,
        )
        handle = await self.gateway.reserve(request)
        if handle.request.estimated_amount < estimate.amount_usd:
            raise ValueError("REPAIR_NODE27_RESERVATION_UNDERFUNDED")
        return BudgetReservation(
            reservation_id=str(handle.reservation_id),
            amount_usd=handle.request.estimated_amount,
            replayed=handle.replayed,
        )

    async def commit(
        self,
        *,
        job: AutoRepairJob,
        reservation: BudgetReservation,
        candidate: RepairCandidate,
        estimate: RepairCostEstimate,
    ) -> None:
        if candidate.provider != estimate.provider or candidate.model != estimate.model:
            raise ValueError("REPAIR_NODE27_SETTLEMENT_ROUTE_MISMATCH")
        if not candidate.provider_request_id:
            raise ValueError("REPAIR_NODE27_PROVIDER_SETTLEMENT_EVIDENCE_REQUIRED")
        if candidate.actual_cost_usd < Decimal("0"):
            raise ValueError("REPAIR_NODE27_ACTUAL_COST_INVALID")
        handle = self._handle(job, reservation, estimate)
        await self.gateway.release(
            handle,
            reason="delegated-cost-settled-downstream",
        )

    async def release(
        self,
        *,
        job: AutoRepairJob,
        reservation: BudgetReservation,
        estimate: RepairCostEstimate,
        reason: str,
    ) -> None:
        handle = self._handle(job, reservation, estimate)
        await self.gateway.release(handle, reason=reason[:128])

    def _handle(
        self,
        job: AutoRepairJob,
        reservation: BudgetReservation,
        estimate: RepairCostEstimate,
    ) -> ReservationHandle:
        request = self._request(
            job=job,
            iteration=job.next_iteration,
            estimate=estimate,
        )
        return ReservationHandle(
            reservation_id=UUID(reservation.reservation_id),
            request=request,
            replayed=reservation.replayed,
        )

    @staticmethod
    def _request(
        *,
        job: AutoRepairJob,
        iteration: int,
        estimate: RepairCostEstimate,
    ) -> BudgetReservationRequest:
        return BudgetReservationRequest(
            context=CostContext(
                organization_id=UUID(job.spec.organization_id),
                project_id=UUID(job.spec.project_id),
                task_id=UUID(job.spec.task_id),
                operation_id=UUID(job.spec.operation_id),
            ),
            provider=estimate.provider,
            model=estimate.model,
            estimated_amount=estimate.amount_usd,
            pricing_snapshot_id=estimate.pricing_snapshot_id,
            confidence=CostConfidence.ESTIMATED,
            reservation_key=f"auto-repair:{job.job_id}:{iteration}",
            metadata={
                "repair_job_id": job.job_id,
                "repair_iteration": iteration,
                "purpose": "repair-budget-envelope",
            },
        )
