from __future__ import annotations

import os
import statistics
import sys
import time
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


def setup_case(identity_type: str):
    scenario = "STRICT_PRESERVE" if identity_type == "LOGO" else "BACKGROUND_REPLACEMENT"
    samples = tuple(
        CalibrationSample(f"p{i}", identity_type, "POSITIVE", score, scenario)
        for i, score in enumerate((98.0, 95.0, 90.0), start=1)
    ) + tuple(
        CalibrationSample(f"n{i}", identity_type, label, score, scenario)
        for i, (label, score) in enumerate(
            (("NEGATIVE", 25.0), ("NEGATIVE", 40.0), ("NEAR_MISS", 72.0)), start=1
        )
    )
    if identity_type == "LOGO":
        weights = {"exact_hash": 0.25, "feature": 0.25, "perceptual": 0.25, "ocr_wordmark": 0.25}
        required = tuple(weights)
        extra_scores = {"feature": 97.0, "perceptual": 96.0}
        ocr_text = "LUMI"
    else:
        weights = {"multimodal": 0.35, "shape": 0.25, "color": 0.15, "brand_region": 0.25}
        required = tuple(weights)
        extra_scores = {"multimodal": 95.0, "shape": 94.0, "color": 92.0, "brand_region": 96.0}
        ocr_text = None
    profile = build_calibration_profile(
        profile_id=f"{identity_type.lower()}-benchmark",
        organization_id="org-bench",
        identity_type=identity_type,
        scenario=scenario,
        version="1",
        model_bundle_version="benchmark@1",
        preprocessor_version="prep@1",
        calibration_dataset_version="benchmark-cal@1",
        signal_weights=weights,
        required_signals=required,
        review_margin=10,
        minimum_confidence=0.7,
        samples=samples,
    )
    identity = IdentityReferenceSet(
        identity_id=f"identity-{identity_type.lower()}",
        organization_id="org-bench",
        identity_type=identity_type,
        canonical_asset_ids=("asset-1",),
        reference_views=(IdentityReferenceView("front", "asset-1", "v1", "org-bench"),),
        threshold_profile_id=profile.profile_id,
        threshold_profile_version=profile.version,
        version="ref@1",
        status="PUBLISHED",
    )
    reference = VerifiedIdentityAsset(
        asset_id="asset-1",
        asset_version="v1",
        organization_id="org-bench",
        checksum_sha256="1" * 64,
        mime_type="image/png",
        rights="USER_OWNED",
        metadata={"ocr_text": "LUMI"} if ocr_text else {},
    )
    candidate = IdentityCandidate(
        organization_id="org-bench",
        artifact_id="artifact-bench",
        artifact_version="1",
        checksum_sha256="1" * 64,
        ocr_text=ocr_text,
        target_region=IdentityRegion(0, 0, 1, 1, "NORMALIZED"),
        signal_scores=extra_scores,
    )
    return identity, profile, reference, candidate, scenario


def run_once(iterations_per_type: int) -> float:
    runtime = IdentityValidationRuntime(
        StructuredIdentitySignalProvider("benchmark", "benchmark@1", "prep@1")
    )
    cases = (setup_case("LOGO"), setup_case("PRODUCT"))
    started = time.perf_counter()
    for identity, profile, reference, candidate, scenario in cases:
        for _ in range(iterations_per_type):
            report = runtime.validate(
                identity=identity,
                profile=profile,
                candidate=candidate,
                references=(reference,),
                severity="HARD",
                scenario=scenario,
            )
            if report.status != "PASS":
                raise RuntimeError("benchmark fixture unexpectedly failed identity validation")
    return (time.perf_counter() - started) * 1000


def main() -> None:
    iterations = int(os.getenv("LUMI_IDENTITY_BENCHMARK_ITERATIONS_PER_TYPE", "1000"))
    budget_ms = float(os.getenv("LUMI_IDENTITY_BENCHMARK_BUDGET_MS", "3000"))
    runs = [run_once(iterations) for _ in range(5)]
    median_ms = statistics.median(runs)
    validations = iterations * 2
    print(
        f"NODE-44 Identity Engine benchmark: {validations} validations, "
        f"median={median_ms:.2f}ms, budget={budget_ms:.2f}ms"
    )
    if median_ms > budget_ms:
        raise SystemExit(
            f"identity benchmark exceeded budget: {median_ms:.2f}ms > {budget_ms:.2f}ms"
        )


if __name__ == "__main__":
    main()
