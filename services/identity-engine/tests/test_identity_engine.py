from __future__ import annotations

import unittest

from lumi_identity_engine import (
    CalibrationSample,
    FaceReferencePolicy,
    IdentityCandidate,
    IdentityReferenceSet,
    IdentityReferenceView,
    IdentityRegion,
    IdentityValidationRuntime,
    StructuredIdentitySignalProvider,
    ThresholdCalibrationProfile,
    VerifiedIdentityAsset,
    build_calibration_profile,
    identity_validation_batch_snapshot_id,
)

H1 = "1" * 64
H2 = "2" * 64


def logo_samples() -> tuple[CalibrationSample, ...]:
    return (
        CalibrationSample("p1", "LOGO", "POSITIVE", 98.0, "STRICT_PRESERVE"),
        CalibrationSample("p2", "LOGO", "POSITIVE", 96.0, "STRICT_PRESERVE"),
        CalibrationSample("p3", "LOGO", "POSITIVE", 92.0, "STRICT_PRESERVE"),
        CalibrationSample("n1", "LOGO", "NEGATIVE", 20.0, "STRICT_PRESERVE"),
        CalibrationSample("n2", "LOGO", "NEGATIVE", 35.0, "STRICT_PRESERVE"),
        CalibrationSample("m1", "LOGO", "NEAR_MISS", 70.0, "STRICT_PRESERVE"),
        CalibrationSample("m2", "LOGO", "NEAR_MISS", 75.0, "STRICT_PRESERVE"),
    )


def profile() -> ThresholdCalibrationProfile:
    return build_calibration_profile(
        profile_id="logo-strict",
        organization_id="org-1",
        identity_type="LOGO",
        scenario="STRICT_PRESERVE",
        version="1",
        model_bundle_version="fixture-model@1",
        preprocessor_version="prep@1",
        calibration_dataset_version="logo-cal@1",
        signal_weights={
            "exact_hash": 0.25,
            "perceptual": 0.2,
            "feature": 0.2,
            "ocr_wordmark": 0.35,
        },
        required_signals=("exact_hash", "perceptual", "feature", "ocr_wordmark"),
        review_margin=10,
        minimum_confidence=0.7,
        samples=logo_samples(),
        minimum_precision=0.95,
        minimum_recall=0.9,
    )


def identity() -> IdentityReferenceSet:
    active_profile = profile()
    return IdentityReferenceSet(
        identity_id="identity-logo",
        organization_id="org-1",
        identity_type="LOGO",
        canonical_asset_ids=("asset-1",),
        reference_views=(IdentityReferenceView("front", "asset-1", "v1", "org-1"),),
        threshold_profile_id=active_profile.profile_id,
        threshold_profile_version=active_profile.version,
        version="ref@1",
        status="PUBLISHED",
    )


def reference() -> VerifiedIdentityAsset:
    return VerifiedIdentityAsset(
        asset_id="asset-1",
        asset_version="v1",
        organization_id="org-1",
        checksum_sha256=H1,
        mime_type="image/png",
        rights="USER_OWNED",
        metadata={"ocr_text": "LUMI COFFEE"},
    )


def candidate(perceptual: object, feature: object, checksum: str = H2) -> IdentityCandidate:
    return IdentityCandidate(
        organization_id="org-1",
        artifact_id="artifact-1",
        artifact_version="7",
        checksum_sha256=checksum,
        ocr_text="LUMI COFFEE",
        target_region=IdentityRegion(0.1, 0.1, 0.5, 0.5, "NORMALIZED"),
        signal_scores={"perceptual": perceptual, "feature": feature},
    )


class IdentityEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = profile()
        self.identity = identity()
        self.provider = StructuredIdentitySignalProvider(
            "structured-fixture", "fixture-model@1", "prep@1"
        )
        self.runtime = IdentityValidationRuntime(self.provider)

    def test_calibration_uses_labeled_dataset(self) -> None:
        self.assertEqual(self.profile.threshold, 92.0)
        self.assertEqual(self.profile.metrics.precision, 1.0)
        self.assertEqual(self.profile.metrics.recall, 1.0)
        self.assertEqual(self.profile.metrics.near_miss_count, 2)

    def test_exact_logo_passes_with_multiple_signals(self) -> None:
        report = self.runtime.validate(
            identity=self.identity,
            profile=self.profile,
            candidate=candidate(99.0, 98.0, H1),
            references=(reference(),),
            severity="HARD",
            scenario="STRICT_PRESERVE",
        )
        self.assertEqual(report.status, "PASS")
        self.assertTrue(report.identity_validation_snapshot_id.startswith("identity-validation:"))
        self.assertEqual(
            tuple(row.signal for row in report.signal_scores),
            ("exact_hash", "feature", "ocr_wordmark", "perceptual"),
        )

    def test_distorted_logo_fails_even_when_wordmark_is_correct(self) -> None:
        report = self.runtime.validate(
            identity=self.identity,
            profile=self.profile,
            candidate=candidate(60.0, 55.0),
            references=(reference(),),
            severity="HARD",
            scenario="STRICT_PRESERVE",
        )
        self.assertEqual(report.status, "FAIL")
        self.assertEqual(report.reason_code, "IDENTITY_SCORE_BELOW_THRESHOLD")

    def test_low_quality_crop_requires_review(self) -> None:
        report = self.runtime.validate(
            identity=self.identity,
            profile=self.profile,
            candidate=candidate(
                {"score": 98.0, "confidence": 0.05},
                {"score": 97.0, "confidence": 0.1},
                H1,
            ),
            references=(reference(),),
            severity="HARD",
            scenario="STRICT_PRESERVE",
        )
        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(report.reason_code, "IDENTITY_CONFIDENCE_BELOW_MINIMUM")

    def test_missing_target_and_required_signal_fail_closed(self) -> None:
        missing_target = IdentityCandidate(
            organization_id="org-1",
            artifact_id="artifact-1",
            artifact_version="7",
            checksum_sha256=H1,
            ocr_text="LUMI COFFEE",
            signal_scores={"perceptual": 99.0, "feature": 98.0},
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY_TARGET_REGION_UNAVAILABLE"):
            self.runtime.validate(
                identity=self.identity,
                profile=self.profile,
                candidate=missing_target,
                references=(reference(),),
                severity="HARD",
                scenario="STRICT_PRESERVE",
            )
        with self.assertRaisesRegex(ValueError, "IDENTITY_REQUIRED_SIGNAL_UNAVAILABLE"):
            self.runtime.validate(
                identity=self.identity,
                profile=self.profile,
                candidate=IdentityCandidate(
                    organization_id="org-1",
                    artifact_id="artifact-1",
                    artifact_version="7",
                    checksum_sha256=H1,
                    ocr_text="LUMI COFFEE",
                    target_region=IdentityRegion(0, 0, 1, 1, "NORMALIZED"),
                    signal_scores={"perceptual": 99.0},
                ),
                references=(reference(),),
                severity="HARD",
                scenario="STRICT_PRESERVE",
            )

    def test_reference_version_and_tenant_are_pinned(self) -> None:
        with self.assertRaisesRegex(ValueError, "IDENTITY_REFERENCE_VERSION_MISMATCH"):
            self.runtime.validate(
                identity=self.identity,
                profile=self.profile,
                candidate=candidate(99.0, 98.0),
                references=(
                    VerifiedIdentityAsset(
                        "asset-1", "v2", "org-1", H1, "image/png", "USER_OWNED"
                    ),
                ),
                severity="HARD",
                scenario="STRICT_PRESERVE",
            )
        with self.assertRaisesRegex(ValueError, "IDENTITY_CANDIDATE_TENANT_MISMATCH"):
            cross_tenant = IdentityCandidate(
                organization_id="org-2",
                artifact_id="artifact-1",
                artifact_version="7",
                target_detected=True,
                signal_scores={"perceptual": 99.0, "feature": 98.0},
            )
            self.runtime.validate(
                identity=self.identity,
                profile=self.profile,
                candidate=cross_tenant,
                references=(reference(),),
                severity="HARD",
                scenario="STRICT_PRESERVE",
            )

    def test_face_processing_is_disabled_by_default(self) -> None:
        face_reference = IdentityReferenceSet(
            identity_id="face-1",
            organization_id="org-1",
            identity_type="FACE",
            canonical_asset_ids=("asset-1",),
            reference_views=(IdentityReferenceView("front", "asset-1", "v1", "org-1"),),
            threshold_profile_id="logo-strict",
            threshold_profile_version="1",
            version="ref@1",
            status="PUBLISHED",
            face_policy=FaceReferencePolicy(
                True,
                "explicit user-requested identity preservation",
                "2026-08-15T00:00:00Z",
            ),
        )
        with self.assertRaisesRegex(ValueError, "FACE_PROCESSING_NOT_ALLOWED"):
            self.runtime.validate(
                identity=face_reference,
                profile=self.profile,
                candidate=candidate(99.0, 98.0),
                references=(reference(),),
                severity="HARD",
                scenario="STRICT_PRESERVE",
            )

    def test_batch_snapshot_is_deterministic(self) -> None:
        report = self.runtime.validate(
            identity=self.identity,
            profile=self.profile,
            candidate=candidate(99.0, 98.0, H1),
            references=(reference(),),
            severity="HARD",
            scenario="STRICT_PRESERVE",
        )
        first = identity_validation_batch_snapshot_id((report,))
        second = identity_validation_batch_snapshot_id((report,))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("identity-batch:"))


if __name__ == "__main__":
    unittest.main()
