from __future__ import annotations

import asyncio

from lumi_visual_critic import (
    ArtifactQualityInput,
    DimensionAssessment,
    GraderCalibrationSnapshot,
    InMemoryQualityResultRepository,
    QualityDimension,
    QualityGateStatus,
    QualityProfileKey,
    QualitySeverity,
    QualitySignalBundle,
    QualityTaskSpec,
    QualityViolation,
    RepairAction,
    RepairActionType,
    VisualCriticEngine,
    VisualGraderResult,
    get_builtin_profile,
)


class Artifacts:
    def __init__(self, *, generation_provider="generator", generation_model="gen-v1"):
        self.artifact = ArtifactQualityInput(
            organization_id="org",
            project_id="project",
            artifact_id="artifact",
            artifact_version_id="version-7",
            artifact_type="IMAGE",
            content_hash="a" * 64,
            primary_file_ref="bucket:key",
            generation_provider=generation_provider,
            generation_model=generation_model,
        )

    def load_exact(self, **kwargs):
        assert kwargs["artifact_version_id"] == "version-7"
        return self.artifact


class CalibrationRegistry:
    def __init__(self, *, fail=False):
        self.fail = fail

    def require_current(self, *, expected):
        if self.fail:
            raise ValueError("stale")


class Signal:
    source_id = "deterministic"
    deterministic = True

    def __init__(self, bundle):
        self.bundle = bundle

    async def evaluate(self, **kwargs):
        return self.bundle


class Visual:
    def __init__(self, result=None, *, fail=False):
        self.result = result
        self.fail = fail
        self.calls = 0

    async def grade(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise TimeoutError("critic timeout")
        return self.result


def calibration(*, calibration_id="cal-1", provider="critic", model="vision-critic-v1"):
    return GraderCalibrationSnapshot(
        calibration_id=calibration_id,
        grader_id="visual-critic-v1",
        provider=provider,
        model=model,
        model_revision="rev-1",
        dataset_hash="b" * 64,
        threshold_version=1,
        sample_count=500,
        precision=0.91,
        recall=0.88,
        false_positive_rate=0.06,
        false_negative_rate=0.12,
        inter_rater_agreement=0.82,
    )


def spec(profile_key=QualityProfileKey.PRODUCTION_WEB, *, cal=None, operation="op"):
    return QualityTaskSpec(
        organization_id="org",
        project_id="project",
        task_id="task",
        operation_id=operation,
        artifact_version_id="version-7",
        profile=get_builtin_profile(profile_key),
        requested_by="user",
        critic_calibration=cal or calibration(),
    )


def assessments(*, low_dimension=None, low_score=100.0, low_confidence=None):
    profile = get_builtin_profile(QualityProfileKey.PRODUCTION_WEB)
    result = []
    for dimension in sorted(profile.required_dimensions, key=lambda item: item.value):
        result.append(
            DimensionAssessment(
                dimension=dimension,
                score=low_score if dimension is low_dimension else 100.0,
                confidence=(
                    low_confidence
                    if dimension is low_dimension and low_confidence is not None
                    else 1.0
                ),
                threshold=profile.thresholds[dimension],
                severity=QualitySeverity.INFO,
                grader_id="deterministic",
            )
        )
    return tuple(result)


def visual_result(*, calibration_id="cal-1"):
    return VisualGraderResult(
        grader_id="visual-critic-v1",
        calibration_id=calibration_id,
        assessments=(),
        violations=(),
        evidence=(),
        strengths=("clear focal point",),
        overall_confidence=0.9,
    )


def run_engine(bundle, *, visual=None, artifacts=None, registry=None, task=None):
    async def scenario():
        engine = VisualCriticEngine(
            artifacts=artifacts or Artifacts(),
            deterministic_signals=(Signal(bundle),),
            visual_grader=visual or Visual(visual_result()),
            calibrations=registry or CalibrationRegistry(),
            repository=InMemoryQualityResultRepository(),
        )
        return await engine.evaluate(task or spec())

    return asyncio.run(scenario())


def test_hard_qr_fail_cannot_be_averaged_away():
    violation = QualityViolation(
        violation_id="qr-hard",
        dimension=QualityDimension.QR_READABILITY,
        code="QR_UNREADABLE",
        severity=QualitySeverity.HARD,
        message="QR decoder failed",
        confidence=1.0,
        blocking=True,
    )
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(),
        violations=(violation,),
        evidence=(),
    )
    visual = Visual(visual_result())
    result = run_engine(bundle, visual=visual)
    assert result.status is QualityGateStatus.FAIL_HARD
    assert result.overall_score == 100.0
    assert visual.calls == 0


def test_product_identity_hard_fail_wins_in_product_strict_profile():
    violation = QualityViolation(
        violation_id="identity-hard",
        dimension=QualityDimension.IDENTITY_CONSISTENCY,
        code="PRODUCT_IDENTITY_DRIFT",
        severity=QualitySeverity.HARD,
        message="Product identity drift",
        confidence=0.99,
        blocking=True,
    )
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(),
        violations=(violation,),
        evidence=(),
    )
    result = run_engine(
        bundle,
        task=spec(QualityProfileKey.PRODUCT_STRICT),
    )
    assert result.status is QualityGateStatus.FAIL_HARD


def test_typography_overflow_is_structured_repairable_failure():
    action = RepairAction(
        action_type=RepairActionType.SET_PROPERTY,
        target="headline",
        reason_code="TEXT_OVERFLOW",
        parameters={"property": "font_size", "value": 28},
        expected_effect=(QualityDimension.TYPOGRAPHY_READABILITY,),
    )
    violation = QualityViolation(
        violation_id="text-overflow",
        dimension=QualityDimension.TYPOGRAPHY_READABILITY,
        code="TEXT_OVERFLOW",
        severity=QualitySeverity.ERROR,
        message="Headline overflows its frame",
        confidence=1.0,
        repair_actions=(action,),
    )
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(
            low_dimension=QualityDimension.TYPOGRAPHY_READABILITY,
            low_score=40,
        ),
        violations=(violation,),
        evidence=(),
    )
    result = run_engine(bundle)
    assert result.status is QualityGateStatus.FAIL_REPAIRABLE
    assert result.repair_actions == (action,)


def test_visual_grader_timeout_never_becomes_pass():
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(),
        violations=(),
        evidence=(),
    )
    result = run_engine(bundle, visual=Visual(fail=True))
    assert result.status is QualityGateStatus.REVIEW_REQUIRED
    assert any(code.startswith("QUALITY_VISUAL_GRADER_FAILED") for code in result.reason_codes)


def test_low_confidence_high_impact_requires_review():
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(
            low_dimension=QualityDimension.CONSTRAINT_COMPLIANCE,
            low_score=100,
            low_confidence=0.2,
        ),
        violations=(),
        evidence=(),
    )
    result = run_engine(bundle)
    assert result.status is QualityGateStatus.REVIEW_REQUIRED
    assert "QUALITY_LOW_CONFIDENCE_HIGH_IMPACT" in result.reason_codes


def test_calibration_mismatch_requires_review():
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(),
        violations=(),
        evidence=(),
    )
    result = run_engine(bundle, visual=Visual(visual_result(calibration_id="wrong")))
    assert result.status is QualityGateStatus.REVIEW_REQUIRED
    assert "QUALITY_CRITIC_CALIBRATION_MISMATCH" in result.reason_codes


def test_same_generation_and_critic_model_requires_review():
    bundle = QualitySignalBundle(
        source_id="deterministic",
        deterministic=True,
        assessments=assessments(),
        violations=(),
        evidence=(),
    )
    result = run_engine(
        bundle,
        artifacts=Artifacts(
            generation_provider="critic",
            generation_model="vision-critic-v1",
        ),
    )
    assert result.status is QualityGateStatus.REVIEW_REQUIRED
    assert "QUALITY_CRITIC_MODEL_ISOLATION_REQUIRED" in result.reason_codes
