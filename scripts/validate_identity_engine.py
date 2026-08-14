from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/identity-engine/src"))

from lumi_identity_engine import (  # noqa: E402
    CalibrationSample,
    IdentityCandidate,
    IdentityReferenceSet,
    IdentityReferenceView,
    IdentityRegion,
    IdentityValidationRuntime,
    StructuredIdentitySignalProvider,
    VerifiedIdentityAsset,
    build_calibration_profile,
)

REQUIRED_FILES = (
    "packages/identity-engine/src/types.ts",
    "packages/identity-engine/src/calibration.ts",
    "packages/identity-engine/src/runtime.ts",
    "packages/identity-engine/src/reference-set.ts",
    "packages/identity-engine/src/compare.ts",
    "packages/identity-engine/src/cache.ts",
    "packages/identity-engine/src/constraint-adapter.ts",
    "packages/identity-engine/src/artifact-gate.ts",
    "services/identity-engine/src/lumi_identity_engine/model.py",
    "services/identity-engine/src/lumi_identity_engine/calibration.py",
    "services/identity-engine/src/lumi_identity_engine/runtime.py",
    "db/migrations/0003_identity_engine.sql",
    "fixtures/identity/node-44-calibration.json",
    "docs/runtime/IDENTITY-ENGINE-V1.md",
    "reports/nodes/NODE-44/calibration.md",
    "reports/nodes/NODE-44/acceptance.md",
    ".github/workflows/identity-engine.yml",
)


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise SystemExit(f"NODE-44 missing required file: {path}")
    return target.read_text(encoding="utf-8")


def require(path: str, *needles: str) -> None:
    text = read(path)
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"NODE-44 contract missing {needle!r} in {path}")


def verify_fixture() -> None:
    payload = json.loads(read("fixtures/identity/node-44-calibration.json"))
    for raw_profile in payload["profiles"]:
        identity_type = raw_profile["identity_type"]
        scenario = raw_profile["scenario"]
        samples = tuple(
            CalibrationSample(
                item["sample_id"],
                identity_type,
                item["label"],
                float(item["score"]),
                scenario,
            )
            for item in raw_profile["samples"]
        )
        profile = build_calibration_profile(
            profile_id=raw_profile["profile_id"],
            organization_id="org-1",
            identity_type=identity_type,
            scenario=scenario,
            version="1",
            model_bundle_version="fixture@1",
            preprocessor_version="prep@1",
            calibration_dataset_version=raw_profile["dataset_version"],
            signal_weights={signal: 1.0 for signal in raw_profile["required_signals"]},
            required_signals=tuple(raw_profile["required_signals"]),
            review_margin=10,
            minimum_confidence=0.7,
            samples=samples,
        )
        if profile.threshold != raw_profile["expected_threshold"]:
            raise SystemExit(
                f"NODE-44 calibration mismatch for {profile.profile_id}: {profile.threshold}"
            )


def verify_runtime_smoke() -> None:
    samples = (
        CalibrationSample("p1", "LOGO", "POSITIVE", 98, "STRICT_PRESERVE"),
        CalibrationSample("p2", "LOGO", "POSITIVE", 92, "STRICT_PRESERVE"),
        CalibrationSample("n1", "LOGO", "NEGATIVE", 20, "STRICT_PRESERVE"),
        CalibrationSample("m1", "LOGO", "NEAR_MISS", 70, "STRICT_PRESERVE"),
    )
    profile = build_calibration_profile(
        profile_id="logo",
        organization_id="org-1",
        identity_type="LOGO",
        scenario="STRICT_PRESERVE",
        version="1",
        model_bundle_version="fixture@1",
        preprocessor_version="prep@1",
        calibration_dataset_version="smoke@1",
        signal_weights={"exact_hash": 0.5, "feature": 0.5},
        required_signals=("exact_hash", "feature"),
        review_margin=10,
        minimum_confidence=0.7,
        samples=samples,
    )
    identity = IdentityReferenceSet(
        "identity-logo",
        "org-1",
        "LOGO",
        ("asset-1",),
        (IdentityReferenceView("front", "asset-1", "v1", "org-1"),),
        profile.profile_id,
        profile.version,
        "ref@1",
        "PUBLISHED",
    )
    reference = VerifiedIdentityAsset(
        "asset-1", "v1", "org-1", "1" * 64, "image/png", "USER_OWNED"
    )
    candidate = IdentityCandidate(
        organization_id="org-1",
        artifact_id="artifact-1",
        artifact_version="1",
        checksum_sha256="1" * 64,
        target_region=IdentityRegion(0, 0, 1, 1, "NORMALIZED"),
        signal_scores={"feature": 98},
    )
    runtime = IdentityValidationRuntime(
        StructuredIdentitySignalProvider("fixture", "fixture@1", "prep@1")
    )
    report = runtime.validate(
        identity=identity,
        profile=profile,
        candidate=candidate,
        references=(reference,),
        severity="HARD",
        scenario="STRICT_PRESERVE",
    )
    if report.status != "PASS" or not report.identity_validation_snapshot_id.startswith(
        "identity-validation:"
    ):
        raise SystemExit("NODE-44 runtime smoke did not produce calibrated PASS")


def main() -> None:
    for path in REQUIRED_FILES:
        read(path)
    require(
        "packages/identity-engine/src/calibration.ts",
        "selectCalibratedThreshold",
        "minimum_precision",
        "near_miss_count",
        "roc_auc",
    )
    require(
        "packages/identity-engine/src/runtime.ts",
        "organization_id: identity.organization_id",
        "IDENTITY_REQUIRED_SIGNAL_UNAVAILABLE",
        "IDENTITY_TARGET_REGION_UNAVAILABLE",
        "identity_validation_snapshot_id",
        "calibration_dataset_version",
    )
    require(
        "packages/identity-engine/src/reference-set.ts",
        "createIdentityReferenceSet",
        "IDENTITY_REFERENCE_ASSET_NOT_READY",
    )
    require(
        "packages/identity-engine/src/compare.ts",
        "compareIdentityCandidates",
        "IDENTITY_COMPARE_TENANT_MISMATCH",
        "IDENTITY_MULTI_SIGNAL_EVIDENCE_REQUIRED",
    )
    require(
        "packages/identity-engine/src/cache.ts",
        "organization_id: input.identity.organization_id",
        "provider_version",
        "preprocessor_version",
    )
    require(
        "packages/identity-engine/src/constraint-adapter.ts",
        "IDENTITY_NUMERIC_THRESHOLD_MUST_COME_FROM_CALIBRATION_PROFILE",
        "IdentitySimilarityValidator",
    )
    require(
        "packages/identity-engine/src/privacy.ts",
        "allow_face_processing: false",
        "allow_persistent_face_index: false",
        "cross_tenant_face_index: false",
    )
    require(
        "db/migrations/0003_identity_engine.sql",
        "profile_id uuid NOT NULL",
        "identity_id uuid NOT NULL",
        "UNIQUE (organization_id, profile_id, version)",
        "UNIQUE (organization_id, identity_id, version)",
        "identity_calibration_samples",
        "identity_validation_reports",
        "persistent_biometric_index = false",
        "REFERENCES artifact_versions(organization_id, id)",
        "identity_validation_snapshot_id",
    )
    verify_fixture()
    verify_runtime_smoke()
    print("NODE-44 Identity Engine contract validation: OK")


if __name__ == "__main__":
    main()
