from __future__ import annotations

from typing import Protocol

from lumi_api.constraint_validator.contracts import ValidationReport
from lumi_auto_repair import (
    AutoRepairJob,
    ConstraintCheck,
    RepairCandidate,
    RepairPlan,
)


class Node39RepairConstraintBackend(Protocol):
    async def validate_repair_plan(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
        repair_kind: str,
        directives: tuple[dict[str, object], ...],
    ) -> ValidationReport: ...

    async def validate_candidate_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> ValidationReport: ...


class Node39RepairConstraintAdapter:
    def __init__(self, backend: Node39RepairConstraintBackend) -> None:
        self.backend = backend

    async def preflight(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> ConstraintCheck:
        report = await self.backend.validate_repair_plan(
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            artifact_version_id=job.working_source.artifact_version_id,
            repair_kind=plan.kind.value,
            directives=tuple(
                {
                    "directive_id": item.directive_id,
                    "source_violation_id": item.source_violation_id,
                    "action_type": item.action_type,
                    "target": item.target,
                    "parameters": item.parameters,
                    "protected_refs": item.protected_refs,
                }
                for item in plan.directives
            ),
        )
        return _check(report)

    async def postflight(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
    ) -> ConstraintCheck:
        report = await self.backend.validate_candidate_version(
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            artifact_version_id=candidate.artifact_version_id,
        )
        return _check(report)


def _check(report: ValidationReport) -> ConstraintCheck:
    blocking = tuple(
        sorted(
            {
                item.type
                for item in report.violations
                if item.blocking
            }
        )
    )
    unavailable = (
        report.status == "VALIDATION_UNAVAILABLE"
        or any(item.unavailable for item in report.violations)
    )
    return ConstraintCheck(
        passed=(report.hard_pass and not blocking and not unavailable),
        blocking_codes=blocking,
        unavailable=unavailable,
        evidence_refs=tuple(report.metrics.validators_run),
    )
