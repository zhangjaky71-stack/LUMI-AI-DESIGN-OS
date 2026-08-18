from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from lumi_api.persistence.models_visual_critic import (
    ArtifactQualityResultModel,
    QualityGraderCalibrationModel,
    QualityProfileSnapshotModel,
)
from lumi_api.visual_critic.codec import decode_calibration, decode_profile, decode_result
from lumi_auto_repair import (
    AutoRepairJob,
    RepairCandidate,
    RepairDirective,
    RepairQualitySnapshot,
)
from lumi_visual_critic import QualitySeverity, QualityTaskSpec, VisualCriticEngine


class Node50RepairQualityAdapter:
    def __init__(self, *, session: Session, critic: VisualCriticEngine) -> None:
        self.session = session
        self.critic = critic

    def get_result(
        self,
        *,
        organization_id: str,
        quality_result_id: str,
    ) -> RepairQualitySnapshot:
        row = self.session.get(ArtifactQualityResultModel, UUID(quality_result_id))
        if row is None:
            raise KeyError("REPAIR_QUALITY_RESULT_NOT_FOUND")
        if str(row.organization_id) != organization_id:
            raise PermissionError("REPAIR_QUALITY_ORGANIZATION_MISMATCH")
        return self._snapshot(decode_result(dict(row.result_json)))

    async def evaluate_candidate(
        self,
        *,
        job: AutoRepairJob,
        candidate: RepairCandidate,
    ) -> RepairQualitySnapshot:
        baseline_row = self.session.get(
            ArtifactQualityResultModel,
            UUID(job.current_quality.quality_result_id),
        )
        if baseline_row is None:
            raise KeyError("REPAIR_BASELINE_QUALITY_NOT_FOUND")
        profile_row = self.session.get(
            QualityProfileSnapshotModel,
            (baseline_row.profile_id, baseline_row.profile_version),
        )
        if profile_row is None:
            raise KeyError("REPAIR_QUALITY_PROFILE_NOT_FOUND")
        profile = decode_profile(dict(profile_row.profile_json))
        calibration = None
        if baseline_row.critic_calibration_id is not None:
            calibration_row = self.session.get(
                QualityGraderCalibrationModel,
                baseline_row.critic_calibration_id,
            )
            if calibration_row is None:
                raise KeyError("REPAIR_CRITIC_CALIBRATION_NOT_FOUND")
            calibration = decode_calibration(dict(calibration_row.calibration_json))
        operation_id = str(
            uuid5(
                NAMESPACE_URL,
                f"lumi:auto-repair-quality:{job.job_id}:{candidate.artifact_version_id}",
            )
        )
        result = await self.critic.evaluate(
            QualityTaskSpec(
                organization_id=job.spec.organization_id,
                project_id=job.spec.project_id,
                task_id=job.spec.task_id,
                operation_id=operation_id,
                artifact_version_id=candidate.artifact_version_id,
                profile=profile,
                requested_by=job.spec.requested_by,
                critic_calibration=calibration,
            )
        )
        return self._snapshot(result)

    @staticmethod
    def _snapshot(result) -> RepairQualitySnapshot:
        directives: list[RepairDirective] = []
        for violation in result.violations:
            for index, action in enumerate(violation.repair_actions):
                directives.append(
                    RepairDirective(
                        directive_id=(
                            f"{violation.violation_id}:{action.action_type.value}:{index}"
                        ),
                        source_violation_id=violation.violation_id,
                        violation_code=violation.code,
                        dimension=violation.dimension.value,
                        severity=violation.severity.value,
                        blocking=violation.blocking,
                        action_type=action.action_type.value,
                        target=action.target,
                        parameters=dict(action.parameters),
                        protected_refs=_protected_refs(
                            action.parameters.get("protected_refs")
                        ),
                    )
                )
        hard_codes = tuple(
            sorted(
                {
                    violation.code
                    for violation in result.violations
                    if violation.blocking or violation.severity is QualitySeverity.HARD
                }
            )
        )
        return RepairQualitySnapshot(
            quality_result_id=result.quality_result_id,
            artifact_version_id=result.artifact_version_id,
            status=result.status.value,
            overall_score=result.overall_score,
            overall_confidence=result.overall_confidence,
            hard_violation_codes=hard_codes,
            directives=tuple(directives),
            profile_id=result.profile_id,
            profile_version=result.profile_version,
            profile_hash=result.profile_hash,
        )


def _protected_refs(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(sorted(str(item) for item in value if str(item)))
    return (str(value),)
