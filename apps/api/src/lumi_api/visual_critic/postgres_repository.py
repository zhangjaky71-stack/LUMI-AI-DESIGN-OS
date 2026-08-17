from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lumi_api.persistence.models_visual_critic import (
    ArtifactQualityResultModel,
    QualityDimensionAssessmentModel,
    QualityGraderCalibrationModel,
    QualityProfileSnapshotModel,
    QualityViolationModel,
)
from lumi_visual_critic.engine import QualityOperationConflict
from lumi_visual_critic.model import (
    GraderCalibrationSnapshot,
    QualityResult,
    QualityTaskSpec,
)

from .codec import (
    decode_calibration,
    decode_result,
    encode_assessment,
    encode_calibration,
    encode_profile,
    encode_result,
    encode_violation,
)


class PostgresGraderCalibrationRegistry:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_current(
        self,
        *,
        expected: GraderCalibrationSnapshot,
    ) -> None:
        row = self.session.get(
            QualityGraderCalibrationModel,
            expected.calibration_id,
        )
        if row is None:
            raise ValueError("QUALITY_CALIBRATION_NOT_REGISTERED")
        if not row.is_current:
            raise ValueError("QUALITY_CALIBRATION_NOT_CURRENT")
        if row.grader_id != expected.grader_id:
            raise ValueError("QUALITY_CALIBRATION_GRADER_MISMATCH")
        if row.calibration_hash != expected.semantic_hash():
            raise ValueError("QUALITY_CALIBRATION_HASH_MISMATCH")
        if (
            row.provider != expected.provider
            or row.model != expected.model
            or row.model_revision != expected.model_revision
        ):
            raise ValueError("QUALITY_CALIBRATION_MODEL_MISMATCH")

    def get(self, calibration_id: str) -> GraderCalibrationSnapshot:
        row = self.session.get(QualityGraderCalibrationModel, calibration_id)
        if row is None:
            raise KeyError("QUALITY_CALIBRATION_NOT_FOUND")
        return decode_calibration(dict(row.calibration_json))


class PostgresQualityResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_operation(
        self,
        *,
        organization_id: str,
        operation_id: str,
    ) -> QualityResult | None:
        row = self.session.scalar(
            select(ArtifactQualityResultModel).where(
                ArtifactQualityResultModel.organization_id == UUID(organization_id),
                ArtifactQualityResultModel.operation_id == UUID(operation_id),
            )
        )
        return None if row is None else decode_result(dict(row.result_json))

    def create(
        self,
        *,
        spec: QualityTaskSpec,
        result: QualityResult,
    ) -> QualityResult:
        existing = self.get_by_operation(
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
        )
        if existing is not None:
            if (
                existing.artifact_version_id != result.artifact_version_id
                or existing.profile_hash != result.profile_hash
                or existing.critic_calibration_hash != result.critic_calibration_hash
            ):
                raise QualityOperationConflict(
                    "QUALITY_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing
        self._ensure_profile(spec)
        if spec.critic_calibration is not None:
            calibration = self.session.get(
                QualityGraderCalibrationModel,
                spec.critic_calibration.calibration_id,
            )
            if calibration is None:
                raise ValueError("QUALITY_CALIBRATION_NOT_REGISTERED")
            if calibration.calibration_hash != spec.critic_calibration.semantic_hash():
                raise ValueError("QUALITY_CALIBRATION_HASH_MISMATCH")
        encoded = encode_result(result)
        result_id = UUID(result.quality_result_id)
        self.session.add(
            ArtifactQualityResultModel(
                quality_result_id=result_id,
                organization_id=UUID(result.organization_id),
                project_id=UUID(result.project_id),
                task_id=UUID(result.task_id),
                operation_id=UUID(result.operation_id),
                artifact_id=UUID(result.artifact_id),
                artifact_version_id=UUID(result.artifact_version_id),
                artifact_content_hash=result.artifact_content_hash,
                profile_id=result.profile_id,
                profile_version=result.profile_version,
                profile_hash=result.profile_hash,
                gate_status=result.status.value,
                overall_score=Decimal(str(result.overall_score)),
                overall_confidence=Decimal(str(result.overall_confidence)),
                critic_grader_id=result.critic_grader_id,
                critic_calibration_id=result.critic_calibration_id,
                critic_calibration_hash=result.critic_calibration_hash,
                result_json=encoded,
            )
        )
        for item in result.assessments:
            self.session.add(
                QualityDimensionAssessmentModel(
                    quality_result_id=result_id,
                    dimension=item.dimension.value,
                    score=Decimal(str(item.score)),
                    confidence=Decimal(str(item.confidence)),
                    threshold=Decimal(str(item.threshold)),
                    severity=item.severity.value,
                    grader_id=item.grader_id,
                    assessment_json=encode_assessment(item),
                )
            )
        for item in result.violations:
            self.session.add(
                QualityViolationModel(
                    quality_result_id=result_id,
                    violation_id=item.violation_id,
                    dimension=item.dimension.value,
                    code=item.code,
                    severity=item.severity.value,
                    confidence=Decimal(str(item.confidence)),
                    blocking=item.blocking,
                    violation_json=encode_violation(item),
                )
            )
        self.session.commit()
        return result

    def _ensure_profile(self, spec: QualityTaskSpec) -> None:
        key = (spec.profile.profile_id, spec.profile.version)
        row = self.session.get(QualityProfileSnapshotModel, key)
        profile_hash = spec.profile.semantic_hash()
        if row is not None:
            if row.profile_hash != profile_hash:
                raise ValueError("QUALITY_PROFILE_VERSION_HASH_CONFLICT")
            return
        self.session.add(
            QualityProfileSnapshotModel(
                profile_id=spec.profile.profile_id,
                version=spec.profile.version,
                profile_key=spec.profile.key.value,
                profile_hash=profile_hash,
                profile_json=encode_profile(spec.profile),
            )
        )
        self.session.flush()


def register_calibration(
    session: Session,
    calibration: GraderCalibrationSnapshot,
    *,
    make_current: bool,
) -> None:
    existing = session.get(
        QualityGraderCalibrationModel,
        calibration.calibration_id,
    )
    calibration_hash = calibration.semantic_hash()
    if existing is not None:
        if existing.calibration_hash != calibration_hash:
            raise ValueError("QUALITY_CALIBRATION_ID_HASH_CONFLICT")
        if make_current and not existing.is_current:
            _retire_current(session, calibration.grader_id)
            existing.is_current = True
            session.commit()
        return
    if make_current:
        _retire_current(session, calibration.grader_id)
    session.add(
        QualityGraderCalibrationModel(
            calibration_id=calibration.calibration_id,
            grader_id=calibration.grader_id,
            provider=calibration.provider,
            model=calibration.model,
            model_revision=calibration.model_revision,
            dataset_hash=calibration.dataset_hash,
            threshold_version=calibration.threshold_version,
            sample_count=calibration.sample_count,
            precision=_decimal_or_none(calibration.precision),
            recall=_decimal_or_none(calibration.recall),
            false_positive_rate=_decimal_or_none(calibration.false_positive_rate),
            false_negative_rate=_decimal_or_none(calibration.false_negative_rate),
            inter_rater_agreement=_decimal_or_none(calibration.inter_rater_agreement),
            calibration_hash=calibration_hash,
            is_current=make_current,
            calibration_json=encode_calibration(calibration),
        )
    )
    session.commit()


def _retire_current(session: Session, grader_id: str) -> None:
    current = session.scalars(
        select(QualityGraderCalibrationModel).where(
            QualityGraderCalibrationModel.grader_id == grader_id,
            QualityGraderCalibrationModel.is_current.is_(True),
        )
    ).all()
    for row in current:
        row.is_current = False
    session.flush()


def _decimal_or_none(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
