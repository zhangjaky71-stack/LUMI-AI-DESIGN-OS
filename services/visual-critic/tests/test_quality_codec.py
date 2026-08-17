from __future__ import annotations

from lumi_api.visual_critic.codec import decode_result, encode_result
from lumi_visual_critic import (
    DimensionAssessment,
    QualityDimension,
    QualityGateStatus,
    QualityProfileKey,
    QualityResult,
    QualitySeverity,
    RepairAction,
    RepairActionType,
    get_builtin_profile,
)


def test_quality_result_codec_round_trip():
    profile = get_builtin_profile(QualityProfileKey.PRODUCTION_WEB)
    action = RepairAction(
        action_type=RepairActionType.SET_PROPERTY,
        target="headline",
        reason_code="TEXT_OVERFLOW",
        parameters={"property": "font_size", "value": 28},
        expected_effect=(QualityDimension.TYPOGRAPHY_READABILITY,),
    )
    assessment = DimensionAssessment(
        dimension=QualityDimension.TYPOGRAPHY_READABILITY,
        score=72,
        confidence=0.96,
        threshold=profile.thresholds[QualityDimension.TYPOGRAPHY_READABILITY],
        severity=QualitySeverity.WARNING,
        grader_id="quality-aggregator/1.0",
    )
    result = QualityResult(
        quality_result_id="11111111-1111-4111-8111-111111111111",
        organization_id="22222222-2222-4222-8222-222222222222",
        project_id="33333333-3333-4333-8333-333333333333",
        task_id="44444444-4444-4444-8444-444444444444",
        operation_id="55555555-5555-4555-8555-555555555555",
        artifact_id="66666666-6666-4666-8666-666666666666",
        artifact_version_id="77777777-7777-4777-8777-777777777777",
        artifact_content_hash="a" * 64,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_hash=profile.semantic_hash(),
        status=QualityGateStatus.FAIL_REPAIRABLE,
        overall_score=72,
        overall_confidence=0.96,
        assessments=(assessment,),
        violations=(),
        evidence=(),
        strengths=("good hierarchy",),
        repair_actions=(action,),
        critic_grader_id="critic-v1",
        critic_calibration_id="cal-v3",
        critic_calibration_hash="b" * 64,
        reason_codes=("QUALITY_SCORE_BELOW_THRESHOLD",),
    )
    assert decode_result(encode_result(result)) == result
