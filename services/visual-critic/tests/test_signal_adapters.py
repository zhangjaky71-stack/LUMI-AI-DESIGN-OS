from __future__ import annotations

import asyncio
from types import SimpleNamespace

from lumi_api.visual_critic.signal_adapters import (
    Node39ConstraintSignalAdapter,
    Node43BrandSignalAdapter,
    Node44IdentitySignalAdapter,
)
from lumi_visual_critic import (
    ArtifactQualityInput,
    GraderCalibrationSnapshot,
    QualityDimension,
    QualityProfileKey,
    QualitySeverity,
    QualityTaskSpec,
    get_builtin_profile,
)


def task() -> QualityTaskSpec:
    return QualityTaskSpec(
        organization_id="org",
        project_id="project",
        task_id="task",
        operation_id="op",
        artifact_version_id="version",
        profile=get_builtin_profile(QualityProfileKey.BRAND_STRICT),
        requested_by="user",
        critic_calibration=GraderCalibrationSnapshot(
            calibration_id="cal",
            grader_id="grader",
            provider="p",
            model="m",
            model_revision="r",
            dataset_hash="a" * 64,
            threshold_version=1,
            sample_count=10,
        ),
    )


def artifact(*, brand=True, identity=True) -> ArtifactQualityInput:
    return ArtifactQualityInput(
        organization_id="org",
        project_id="project",
        artifact_id="artifact",
        artifact_version_id="version",
        artifact_type="IMAGE",
        content_hash="b" * 64,
        primary_file_ref="bucket:key",
        brand_rule_snapshot_id="brand-v1" if brand else None,
        identity_refs=("identity-v1",) if identity else (),
    )


class ConstraintBackend:
    async def validate_exact(self, **kwargs):
        return SimpleNamespace(
            status="BLOCKED",
            hard_pass=False,
            health_score=95.0,
            metrics=SimpleNamespace(
                validators_run=("QRValidator", "TextOverflowValidator"),
                violations_count=1,
                blocking_count=1,
            ),
            violations=(
                SimpleNamespace(
                    violation_id="qr-1",
                    type="QR_READABLE",
                    validator="QRValidator",
                    severity="HARD",
                    affected_node_ids=("qr",),
                    message="QR cannot decode",
                    suggested_fix_operations=(),
                    blocking=True,
                    unavailable=False,
                ),
            ),
        )


class BrandBackend:
    async def validate_brand(self, **kwargs):
        severity = SimpleNamespace(value="HARD")
        violation = SimpleNamespace(
            rule_id="rule-font",
            rule_key="FONT_ALLOWED.primary",
            severity=severity,
            node_id="headline",
            code="FONT_NOT_ALLOWED",
            unavailable=False,
            blocking=True,
        )
        return SimpleNamespace(
            rule_set_id="ruleset",
            rule_set_version=3,
            score=62.0,
            can_approve=False,
            violations=(violation,),
        )


class IdentityBackend:
    async def validate_identities(self, **kwargs):
        return (
            SimpleNamespace(
                identity_id="product-id",
                reference_version=4,
                reference_snapshot_hash="c" * 64,
                identity_type=SimpleNamespace(value="PRODUCT"),
                status=SimpleNamespace(value="BLOCKED"),
                identity_score=55.0,
                confidence=0.98,
                threshold_profile=SimpleNamespace(
                    profile_key="product-strict",
                    version=2,
                    severity=SimpleNamespace(value="HARD"),
                ),
                signal_scores=(),
                region=None,
                evidence_refs=("feature-match",),
                failure_codes=("PRODUCT_IDENTITY_DRIFT",),
                provider_version="identity/4",
                candidate_node_id="product",
            ),
        )


def test_node39_qr_hard_fail_is_blocking_quality_violation():
    async def scenario():
        result = await Node39ConstraintSignalAdapter(ConstraintBackend()).evaluate(
            spec=task(), artifact=artifact()
        )
        violation = result.violations[0]
        assert violation.dimension is QualityDimension.QR_READABILITY
        assert violation.severity is QualitySeverity.HARD
        assert violation.blocking is True
        qr = next(
            item for item in result.assessments
            if item.dimension is QualityDimension.QR_READABILITY
        )
        assert qr.score == 0.0

    asyncio.run(scenario())


def test_node43_brand_font_hard_fail_maps_to_brand_consistency():
    async def scenario():
        result = await Node43BrandSignalAdapter(BrandBackend()).evaluate(
            spec=task(), artifact=artifact()
        )
        violation = result.violations[0]
        assert violation.code == "FONT_NOT_ALLOWED"
        assert violation.dimension is QualityDimension.BRAND_CONSISTENCY
        assert violation.blocking is True

    asyncio.run(scenario())


def test_node44_product_identity_fail_is_hard():
    async def scenario():
        result = await Node44IdentitySignalAdapter(IdentityBackend()).evaluate(
            spec=task(), artifact=artifact()
        )
        violation = result.violations[0]
        assert violation.dimension is QualityDimension.IDENTITY_CONSISTENCY
        assert violation.severity is QualitySeverity.HARD
        assert violation.blocking is True
        assert result.assessments[0].score == 55.0

    asyncio.run(scenario())
