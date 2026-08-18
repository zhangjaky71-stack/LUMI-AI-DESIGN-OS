from __future__ import annotations

from typing import Protocol

from lumi_auto_repair import (
    AutoRepairJob,
    BudgetReservation,
    RepairCandidate,
    RepairCostEstimate,
    RepairKind,
    RepairPlan,
)


class Node38StructuralRepairBackend(Protocol):
    async def execute_design_ops(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
    ) -> RepairCandidate: ...


class Node47LocalImageRepairBackend(Protocol):
    async def estimate_local_edit(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> RepairCostEstimate: ...

    async def execute_local_edit(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
    ) -> RepairCandidate: ...


class GenerationRepairBackend(Protocol):
    async def estimate_regeneration(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> RepairCostEstimate: ...

    async def execute_regeneration(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
        reservation: BudgetReservation,
    ) -> RepairCandidate: ...


class CompositeRepairExecutor:
    """Dispatch repair kinds without leaking provider logic into the service."""

    def __init__(
        self,
        *,
        structural: Node38StructuralRepairBackend,
        local_image: Node47LocalImageRepairBackend,
        generation: GenerationRepairBackend,
    ) -> None:
        self.structural = structural
        self.local_image = local_image
        self.generation = generation

    async def estimate(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> RepairCostEstimate:
        if plan.kind in {
            RepairKind.STRUCTURAL_DESIGN_OP,
            RepairKind.COPY_TYPOGRAPHY_FIX,
        }:
            return RepairCostEstimate(
                amount_usd=plan.estimated_cost_usd,
                provider="internal",
                model="node38-design-ir-runtime",
                pricing_snapshot_id=None,
            )
        if plan.kind is RepairKind.LOCAL_IMAGE_EDIT:
            return await self.local_image.estimate_local_edit(job=job, plan=plan)
        if plan.kind in {
            RepairKind.REGENERATE_ELEMENT,
            RepairKind.REGENERATE_ARTIFACT,
        }:
            return await self.generation.estimate_regeneration(job=job, plan=plan)
        raise ValueError("REPAIR_EXECUTOR_KIND_UNSUPPORTED")

    async def execute(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
        reservation: BudgetReservation | None,
    ) -> RepairCandidate:
        if plan.kind in {
            RepairKind.STRUCTURAL_DESIGN_OP,
            RepairKind.COPY_TYPOGRAPHY_FIX,
        }:
            if reservation is not None:
                raise ValueError("REPAIR_STRUCTURAL_RESERVATION_FORBIDDEN")
            candidate = await self.structural.execute_design_ops(
                job=job,
                plan=plan,
                repair_branch_id=repair_branch_id,
            )
            if candidate.actual_cost_usd != 0:
                raise ValueError("REPAIR_STRUCTURAL_COST_MUST_BE_ZERO")
            return candidate

        if reservation is None:
            raise ValueError("REPAIR_PAID_RESERVATION_REQUIRED")
        if plan.kind is RepairKind.LOCAL_IMAGE_EDIT:
            # The NODE-51 reservation is only a repair-loop budget envelope.
            # NODE-47 performs its own provider settlement through Model Gateway.
            return await self.local_image.execute_local_edit(
                job=job,
                plan=plan,
                repair_branch_id=repair_branch_id,
            )
        if plan.kind in {
            RepairKind.REGENERATE_ELEMENT,
            RepairKind.REGENERATE_ARTIFACT,
        }:
            return await self.generation.execute_regeneration(
                job=job,
                plan=plan,
                repair_branch_id=repair_branch_id,
                reservation=reservation,
            )
        raise ValueError("REPAIR_EXECUTOR_KIND_UNSUPPORTED")
