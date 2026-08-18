from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from lumi_auto_repair import (
    AutoRepairJob,
    BudgetReservation,
    RepairCandidate,
    RepairCostEstimate,
    RepairPlan,
)


class Node27BudgetBackend(Protocol):
    async def reserve_repair_budget(
        self,
        *,
        organization_id: str,
        project_id: str,
        task_id: str,
        operation_id: str,
        repair_job_id: str,
        iteration: int,
        provider: str,
        model: str,
        pricing_snapshot_id: str | None,
        estimated_amount_usd: str,
    ) -> tuple[str, str, bool]:
        """Return reservation id, reserved amount decimal string, replayed."""
        ...

    async def release_repair_budget(
        self,
        *,
        reservation_id: str,
        organization_id: str,
        operation_id: str,
        reason: str,
    ) -> None: ...


class Node27RepairBudgetAdapter:
    """Reserve a loop-level budget envelope without double-booking provider cost.

    NODE-47/NODE-46 paid execution already settles the authoritative provider
    ActualCost through Model Gateway + NODE-27. NODE-51 therefore uses this
    reservation only to prevent the repair loop from starting work outside its
    remaining budget. After a successful paid execution the envelope is released;
    the candidate's actual_cost_usd is used only for the loop's own cumulative
    budget and must match the downstream provider settlement evidence.
    """

    def __init__(self, backend: Node27BudgetBackend) -> None:
        self.backend = backend

    async def reserve(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        estimate: RepairCostEstimate,
    ) -> BudgetReservation:
        reservation_id, amount, replayed = await self.backend.reserve_repair_budget(
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            task_id=job.spec.task_id,
            operation_id=job.spec.operation_id,
            repair_job_id=job.job_id,
            iteration=plan.iteration,
            provider=estimate.provider,
            model=estimate.model,
            pricing_snapshot_id=estimate.pricing_snapshot_id,
            estimated_amount_usd=str(estimate.amount_usd),
        )
        reserved = Decimal(amount)
        if reserved < estimate.amount_usd:
            raise ValueError("REPAIR_NODE27_RESERVATION_UNDERFUNDED")
        return BudgetReservation(
            reservation_id=reservation_id,
            amount_usd=reserved,
            replayed=replayed,
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
        if candidate.actual_cost_usd < 0:
            raise ValueError("REPAIR_NODE27_ACTUAL_COST_INVALID")
        if not candidate.provider_request_id:
            raise ValueError("REPAIR_NODE27_PROVIDER_SETTLEMENT_EVIDENCE_REQUIRED")
        await self.backend.release_repair_budget(
            reservation_id=reservation.reservation_id,
            organization_id=job.spec.organization_id,
            operation_id=job.spec.operation_id,
            reason=(
                "delegated-provider-cost-settled-downstream:"
                f"{candidate.provider_request_id}"
            )[:128],
        )

    async def release(
        self,
        *,
        job: AutoRepairJob,
        reservation: BudgetReservation,
        estimate: RepairCostEstimate,
        reason: str,
    ) -> None:
        await self.backend.release_repair_budget(
            reservation_id=reservation.reservation_id,
            organization_id=job.spec.organization_id,
            operation_id=job.spec.operation_id,
            reason=reason,
        )
