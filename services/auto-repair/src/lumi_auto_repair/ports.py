from __future__ import annotations

from typing import Protocol

from .costing import RepairCostEstimate
from .model import (
    AutoRepairJob,
    AutoRepairTaskSpec,
    BudgetReservation,
    ConstraintCheck,
    RepairCandidate,
    RepairPlan,
    RepairQualitySnapshot,
    RepairSourceSnapshot,
)


class RepairArtifactPort(Protocol):
    def load_source_exact(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> RepairSourceSnapshot: ...

    def fork_repair_branch(
        self,
        *,
        source: RepairSourceSnapshot,
        repair_job_id: str,
        iteration: int,
        actor_id: str,
    ) -> str: ...

    def promote_candidate(
        self,
        *,
        original_source: RepairSourceSnapshot,
        candidate: RepairCandidate,
        repair_job_id: str,
        actor_id: str,
    ) -> RepairCandidate: ...

    def approve_promoted_version(
        self,
        *,
        promoted: RepairCandidate,
        quality: RepairQualitySnapshot,
        repair_job_id: str,
    ) -> str: ...


class RepairQualityPort(Protocol):
    def get_result(
        self,
        *,
        organization_id: str,
        quality_result_id: str,
    ) -> RepairQualitySnapshot: ...

    async def evaluate_candidate(
        self,
        *,
        job: AutoRepairJob,
        candidate: RepairCandidate,
    ) -> RepairQualitySnapshot: ...


class RepairConstraintPort(Protocol):
    async def preflight(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> ConstraintCheck: ...

    async def postflight(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
    ) -> ConstraintCheck: ...


class RepairExecutorPort(Protocol):
    async def estimate(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> RepairCostEstimate: ...

    async def execute(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
        reservation: BudgetReservation | None,
    ) -> RepairCandidate: ...


class RepairBudgetPort(Protocol):
    async def reserve(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        estimate: RepairCostEstimate,
    ) -> BudgetReservation: ...

    async def commit(
        self,
        *,
        job: AutoRepairJob,
        reservation: BudgetReservation,
        candidate: RepairCandidate,
        estimate: RepairCostEstimate,
    ) -> None: ...

    async def release(
        self,
        *,
        job: AutoRepairJob,
        reservation: BudgetReservation,
        estimate: RepairCostEstimate,
        reason: str,
    ) -> None: ...


class AutoRepairRepositoryPort(Protocol):
    def create(self, job: AutoRepairJob) -> AutoRepairJob: ...

    def get(self, job_id: str) -> AutoRepairJob: ...

    def save(self, job: AutoRepairJob) -> AutoRepairJob: ...

    def get_by_operation(
        self,
        *,
        organization_id: str,
        operation_id: str,
    ) -> AutoRepairJob | None: ...


class RepairPlannerPort(Protocol):
    def plan(
        self,
        *,
        spec: AutoRepairTaskSpec,
        job: AutoRepairJob,
    ) -> RepairPlan: ...
