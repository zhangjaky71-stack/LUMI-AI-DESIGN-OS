from __future__ import annotations

from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from .model import (
    ArtifactQualityInput,
    DimensionAssessment,
    QualityDimension,
    QualityGateStatus,
    QualityResult,
    QualitySeverity,
    QualitySignalBundle,
    QualityTaskSpec,
    QualityViolation,
    VisualGraderResult,
)
from .ports import (
    ArtifactQualityInputPort,
    GraderCalibrationPort,
    QualityResultRepositoryPort,
    QualitySignalPort,
    VisualGraderPort,
)


class QualityOperationConflict(RuntimeError):
    pass


class VisualCriticEngine:
    """Hard gates and deterministic evidence always outrank model scoring."""

    def __init__(
        self,
        *,
        artifacts: ArtifactQualityInputPort,
        deterministic_signals: tuple[QualitySignalPort, ...],
        visual_grader: VisualGraderPort | None,
        calibrations: GraderCalibrationPort,
        repository: QualityResultRepositoryPort,
    ) -> None:
        if not deterministic_signals:
            raise ValueError("QUALITY_DETERMINISTIC_SIGNALS_REQUIRED")
        if any(not item.deterministic for item in deterministic_signals):
            raise ValueError("QUALITY_DETERMINISTIC_PORT_MARKED_NONDETERMINISTIC")
        self.artifacts = artifacts
        self.deterministic_signals = deterministic_signals
        self.visual_grader = visual_grader
        self.calibrations = calibrations
        self.repository = repository

    async def evaluate(self, spec: QualityTaskSpec) -> QualityResult:
        existing = self.repository.get_by_operation(
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
        )
        if existing is not None:
            if (
                existing.artifact_version_id != spec.artifact_version_id
                or existing.profile_hash != spec.profile.semantic_hash()
            ):
                raise QualityOperationConflict(
                    "QUALITY_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing

        artifact = self.artifacts.load_exact(
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            artifact_version_id=spec.artifact_version_id,
        )
        if artifact.artifact_version_id != spec.artifact_version_id:
            raise ValueError("QUALITY_EXACT_ARTIFACT_VERSION_MISMATCH")

        deterministic: list[QualitySignalBundle] = []
        unavailable_sources: list[str] = []
        for port in self.deterministic_signals:
            try:
                signal = await port.evaluate(spec=spec, artifact=artifact)
            except Exception as exc:
                signal = QualitySignalBundle(
                    source_id=port.source_id,
                    deterministic=True,
                    assessments=(),
                    violations=(),
                    evidence=(),
                    unavailable_reason=type(exc).__name__,
                )
            deterministic.append(signal)
            if signal.unavailable_reason:
                unavailable_sources.append(signal.source_id)

        hard_violations = tuple(
            violation
            for bundle in deterministic
            for violation in bundle.violations
            if violation.blocking or violation.severity is QualitySeverity.HARD
        )
        if hard_violations:
            result = self._build_result(
                spec=spec,
                artifact=artifact,
                deterministic=tuple(deterministic),
                visual=None,
                forced_status=QualityGateStatus.FAIL_HARD,
                extra_reasons=("QUALITY_HARD_GATE_FAILED",),
            )
            return self.repository.create(spec=spec, result=result)

        visual: VisualGraderResult | None = None
        visual_failure: str | None = None
        calibration = spec.critic_calibration
        if spec.profile.visual_grader_required:
            if calibration is None:
                visual_failure = "QUALITY_CRITIC_CALIBRATION_REQUIRED"
            elif self.visual_grader is None:
                visual_failure = "QUALITY_VISUAL_GRADER_UNAVAILABLE"
            elif (
                artifact.generation_provider
                and artifact.generation_model
                and calibration.provider == artifact.generation_provider
                and calibration.model == artifact.generation_model
            ):
                visual_failure = "QUALITY_CRITIC_MODEL_ISOLATION_REQUIRED"
            else:
                try:
                    self.calibrations.require_current(expected=calibration)
                    visual = await self.visual_grader.grade(
                        spec=spec,
                        artifact=artifact,
                        deterministic_signals=tuple(deterministic),
                    )
                    if visual.calibration_id != calibration.calibration_id:
                        visual = None
                        visual_failure = "QUALITY_CRITIC_CALIBRATION_MISMATCH"
                    elif visual.grader_id != calibration.grader_id:
                        visual = None
                        visual_failure = "QUALITY_CRITIC_GRADER_ID_MISMATCH"
                except Exception as exc:
                    visual_failure = f"QUALITY_VISUAL_GRADER_FAILED:{type(exc).__name__}"

        forced_status: QualityGateStatus | None = None
        reasons: list[str] = []
        if unavailable_sources:
            reasons.append("QUALITY_DETERMINISTIC_SIGNAL_UNAVAILABLE")
        if visual_failure:
            forced_status = QualityGateStatus.REVIEW_REQUIRED
            reasons.append(visual_failure)

        result = self._build_result(
            spec=spec,
            artifact=artifact,
            deterministic=tuple(deterministic),
            visual=visual,
            forced_status=forced_status,
            extra_reasons=tuple(reasons),
        )
        return self.repository.create(spec=spec, result=result)

    def _build_result(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
        deterministic: tuple[QualitySignalBundle, ...],
        visual: VisualGraderResult | None,
        forced_status: QualityGateStatus | None,
        extra_reasons: tuple[str, ...],
    ) -> QualityResult:
        all_assessments = [
            assessment
            for bundle in deterministic
            for assessment in bundle.assessments
        ]
        all_violations = [
            violation
            for bundle in deterministic
            for violation in bundle.violations
        ]
        all_evidence = [
            evidence for bundle in deterministic for evidence in bundle.evidence
        ]
        strengths: tuple[str, ...] = ()
        if visual is not None:
            all_assessments.extend(visual.assessments)
            all_violations.extend(visual.violations)
            all_evidence.extend(visual.evidence)
            strengths = visual.strengths

        assessments = self._aggregate_dimensions(
            tuple(all_assessments),
            deterministic_sources=tuple(deterministic),
            profile=spec.profile,
        )
        by_dimension = {item.dimension: item for item in assessments}
        missing = tuple(
            sorted(
                spec.profile.required_dimensions - set(by_dimension),
                key=lambda item: item.value,
            )
        )
        score = self._weighted_score(assessments, spec.profile.weights)
        confidence = self._weighted_confidence(
            assessments,
            spec.profile.weights,
        )
        reasons = list(extra_reasons)
        status = forced_status

        blocking = tuple(item for item in all_violations if item.blocking)
        if blocking:
            status = QualityGateStatus.FAIL_HARD
            reasons.append("QUALITY_HARD_GATE_FAILED")
        elif missing:
            status = QualityGateStatus.REVIEW_REQUIRED
            reasons.append("QUALITY_REQUIRED_DIMENSION_MISSING")
        elif self._low_confidence_high_impact(
            assessments=assessments,
            violations=tuple(all_violations),
            low_confidence_threshold=spec.profile.low_confidence_threshold,
            hard_dimensions=spec.profile.hard_dimensions,
        ):
            status = QualityGateStatus.REVIEW_REQUIRED
            reasons.append("QUALITY_LOW_CONFIDENCE_HIGH_IMPACT")
        elif status is None:
            below = tuple(
                item
                for item in assessments
                if item.score < spec.profile.thresholds[item.dimension]
            )
            repairable = any(item.repair_actions for item in all_violations)
            if below or score < spec.profile.overall_pass_threshold:
                status = (
                    QualityGateStatus.FAIL_REPAIRABLE
                    if repairable
                    else QualityGateStatus.REVIEW_REQUIRED
                )
                reasons.append(
                    "QUALITY_SCORE_BELOW_THRESHOLD"
                    if repairable
                    else "QUALITY_FAILURE_WITHOUT_REGISTERED_REPAIR"
                )
            elif (
                score < spec.profile.warning_threshold
                or any(
                    item.severity in {QualitySeverity.WARNING, QualitySeverity.ERROR}
                    for item in all_violations
                )
            ):
                status = QualityGateStatus.PASS_WITH_WARNINGS
                reasons.append("QUALITY_NONBLOCKING_WARNINGS")
            else:
                status = QualityGateStatus.PASS
                reasons.append("QUALITY_GATE_PASSED")

        repair_actions = self._dedupe_repairs(tuple(all_violations))
        calibration = spec.critic_calibration
        return QualityResult(
            quality_result_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"lumi:quality-result:{spec.organization_id}:{spec.operation_id}",
                )
            ),
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            task_id=spec.task_id,
            operation_id=spec.operation_id,
            artifact_id=artifact.artifact_id,
            artifact_version_id=artifact.artifact_version_id,
            artifact_content_hash=artifact.content_hash,
            profile_id=spec.profile.profile_id,
            profile_version=spec.profile.version,
            profile_hash=spec.profile.semantic_hash(),
            status=status,
            overall_score=round(score, 4),
            overall_confidence=round(confidence, 6),
            assessments=assessments,
            violations=tuple(all_violations),
            evidence=tuple(all_evidence),
            strengths=strengths,
            repair_actions=repair_actions,
            critic_grader_id=(visual.grader_id if visual else None),
            critic_calibration_id=(calibration.calibration_id if calibration else None),
            critic_calibration_hash=(
                calibration.semantic_hash() if calibration else None
            ),
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    @staticmethod
    def _aggregate_dimensions(
        assessments: tuple[DimensionAssessment, ...],
        *,
        deterministic_sources: tuple[QualitySignalBundle, ...],
        profile,
    ) -> tuple[DimensionAssessment, ...]:
        deterministic_ids = {
            assessment.grader_id
            for bundle in deterministic_sources
            for assessment in bundle.assessments
            if assessment.grader_id is not None
        }
        grouped: dict[QualityDimension, list[DimensionAssessment]] = {}
        for assessment in assessments:
            grouped.setdefault(assessment.dimension, []).append(assessment)
        aggregated: list[DimensionAssessment] = []
        for dimension in sorted(grouped, key=lambda item: item.value):
            values = grouped[dimension]
            total_weight = 0.0
            score_sum = 0.0
            confidence_sum = 0.0
            evidence_ids: list[str] = []
            severity = QualitySeverity.INFO
            for item in values:
                priority = 2.0 if item.grader_id in deterministic_ids else 1.0
                weight = max(item.confidence, 0.05) * priority
                total_weight += weight
                score_sum += item.score * weight
                confidence_sum += item.confidence * weight
                evidence_ids.extend(item.evidence_ids)
                severity = _max_severity(severity, item.severity)
            aggregated.append(
                DimensionAssessment(
                    dimension=dimension,
                    score=score_sum / total_weight,
                    confidence=confidence_sum / total_weight,
                    threshold=profile.thresholds[dimension],
                    severity=severity,
                    evidence_ids=tuple(dict.fromkeys(evidence_ids)),
                    grader_id="quality-aggregator/1.0",
                )
            )
        return tuple(aggregated)

    @staticmethod
    def _weighted_score(
        assessments: tuple[DimensionAssessment, ...],
        weights: dict[QualityDimension, float],
    ) -> float:
        if not assessments:
            return 0.0
        total = sum(weights[item.dimension] for item in assessments)
        if total <= 0:
            return 0.0
        return sum(
            item.score * weights[item.dimension] for item in assessments
        ) / total

    @staticmethod
    def _weighted_confidence(
        assessments: tuple[DimensionAssessment, ...],
        weights: dict[QualityDimension, float],
    ) -> float:
        if not assessments:
            return 0.0
        total = sum(weights[item.dimension] for item in assessments)
        if total <= 0:
            return 0.0
        return sum(
            item.confidence * weights[item.dimension] for item in assessments
        ) / total

    @staticmethod
    def _low_confidence_high_impact(
        *,
        assessments: tuple[DimensionAssessment, ...],
        violations: tuple[QualityViolation, ...],
        low_confidence_threshold: float,
        hard_dimensions: frozenset[QualityDimension],
    ) -> bool:
        for item in assessments:
            if (
                item.dimension in hard_dimensions
                and item.confidence < low_confidence_threshold
            ):
                return True
        return any(
            violation.severity in {QualitySeverity.ERROR, QualitySeverity.HARD}
            and violation.confidence < low_confidence_threshold
            for violation in violations
        )

    @staticmethod
    def _dedupe_repairs(
        violations: tuple[QualityViolation, ...],
    ):
        seen: set[tuple[str, str, str]] = set()
        result = []
        for violation in violations:
            for action in violation.repair_actions:
                key = (
                    action.action_type.value,
                    action.target,
                    action.reason_code,
                )
                if key not in seen:
                    seen.add(key)
                    result.append(action)
        return tuple(result)


def _max_severity(left: QualitySeverity, right: QualitySeverity) -> QualitySeverity:
    rank = {
        QualitySeverity.INFO: 0,
        QualitySeverity.WARNING: 1,
        QualitySeverity.ERROR: 2,
        QualitySeverity.HARD: 3,
    }
    return left if rank[left] >= rank[right] else right
