from __future__ import annotations

from typing import Protocol

from lumi_auto_repair import (
    AutoRepairJob,
    BudgetReservation,
    RepairCandidate,
    RepairPlan,
)
from lumi_auto_repair.costing import RepairCostEstimate


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

    async def commit_repair_budget(
        self,
        *,
        reservation_id: str,
        organization_id: str,
        operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        actual_amount_usd: str,
        pricing_snapshot_id: str | None,
    ) -> None: ...

    async def release_repair_budget(
        self,
        *,
        reservation_id: str,
        organization_id: str,
        operation_id: str,
        reason: str,
    ) -> None: ...


class Node27RepairBudgetAdapter:
    """Thin bridge; NODE-27 remains the only monetary source of truth."""

    def __init__(self, backend: Node27BudgetBackend) -> None:
        self.backend = backend

    async def reserve(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        estimate: RepairCostEstimate,
    ) -> BudgetReservation:
        reservation_id, amount, replayed = (
            await self.backend.reserve_repair_budget(
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
        )
        from decimal import Decimal

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
        await self.backend.commit_repair_budget(
            reservation_id=reservation.reservation_id,
            organization_id=job.spec.organization_id,
            operation_id=job.spec.operation_id,
            provider=estimate.provider,
            model=estimate.model,
            provider_request_id=candidate.provider_request_id,
            actual_amount_usd=str(candidate.actual_cost_usd),
            pricing_snapshot_id=estimate.pricing_snapshot_id,
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
