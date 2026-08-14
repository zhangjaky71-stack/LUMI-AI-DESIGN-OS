from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "packages/quality-engine/package.json",
    "packages/quality-engine/src/types.ts",
    "packages/quality-engine/src/engine.ts",
    "packages/quality-engine/src/deterministic.ts",
    "packages/quality-engine/src/profiles.ts",
    "packages/quality-engine/src/calibration.ts",
    "packages/quality-engine/src/artifact-adapter.ts",
    "packages/quality-engine/src/quality-engine.test.ts",
    "packages/quality-engine/src/artifact-adapter.test.ts",
    "packages/quality-engine/src/calibration-fixture.test.ts",
    "packages/quality-engine/src/quality-benchmark.test.ts",
    "fixtures/quality/node-50-calibration.json",
    "evals/datasets/visual-critic/suite.json",
    "evals/datasets/visual-critic/v1/cases.json",
    "evals/fixtures/visual-critic/baseline.json",
    "evals/fixtures/visual-critic/candidate.json",
    "db/migrations/0009_visual_critic.sql",
    "docs/nodes/NODE-50-VISUAL-CRITIC.md",
    "docs/runtime/VISUAL-CRITIC-V1.md",
    "reports/nodes/NODE-50/acceptance.md",
    "reports/nodes/NODE-50/calibration.md",
    ".github/workflows/visual-critic.yml",
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    for path in REQUIRED:
        require((ROOT / path).is_file(), f"missing NODE-50 file: {path}")

    engine = read("packages/quality-engine/src/engine.ts")
    types = read("packages/quality-engine/src/types.ts")
    deterministic = read("packages/quality-engine/src/deterministic.ts")
    ports = read("packages/quality-engine/src/ports.ts")
    calibration = read("packages/quality-engine/src/calibration.ts")
    artifact = read("packages/quality-engine/src/artifact-adapter.ts")
    migration = read("db/migrations/0009_visual_critic.sql")
    workflow = read(".github/workflows/visual-critic.yml")

    for status in ["PASS", "PASS_WITH_WARNINGS", "FAIL_REPAIRABLE", "FAIL_HARD", "REVIEW_REQUIRED"]:
        require(f'"{status}"' in types, f"missing quality status {status}")
    for dimension in ["CONSTRAINT_COMPLIANCE", "COMPOSITION", "VISUAL_HIERARCHY", "ALIGNMENT_SPACING", "TYPOGRAPHY_READABILITY", "CONTRAST", "BRAND_CONSISTENCY", "IDENTITY_CONSISTENCY", "TEXT_ACCURACY", "LOGO_INTEGRITY", "QR_READABILITY", "IMAGE_DEFECTS", "RESOLUTION_EXPORT_READINESS"]:
        require(f'"{dimension}"' in types, f"missing quality dimension {dimension}")

    require("evaluateDeterministicSignals(subject)" in engine, "deterministic graders must run in core critic path")
    require('status = "FAIL_HARD"' in engine, "hard failure status gate missing")
    require("lowConfidenceHard" in engine and 'status = "REVIEW_REQUIRED"' in engine, "low-confidence fail-closed review gate missing")
    require("QUALITY_CRITIC_ROLE_ISOLATION_REQUIRED" in engine, "independent critic role gate missing")
    require("visual-grader:not-isolated" in engine, "same model/prompt self-approval guard missing")
    require("DESIGN_OPERATION_TYPES" in engine and "dedupeOperations" in engine, "repair actions must be frozen DesignOperations")
    require("executeOperations" not in engine and ".transition(" not in engine, "Visual Critic must not mutate Design IR or Artifact status")
    require("REQUIRE_SCANNABILITY" in engine and "REQUIRE_IDENTITY_SCORE" in engine and "REQUIRE_BRAND_COMPLIANCE" in engine, "NODE-39 signal delegation missing")
    require("BrandComplianceReport" in ports and "IdentityValidationReport" in ports and "PostflightReport" in ports, "NODE-39/43/44 typed ports missing")
    require('role_id: "visual-critic"' in ports, "visual grader role contract missing")

    provider_markers = ["openai", "anthropic", "google.generativeai", "@google/generative-ai", "replicate", "fal-ai"]
    package_text = "\n".join(read(str(path.relative_to(ROOT))) for path in (ROOT / "packages/quality-engine/src").glob("*.ts"))
    lower = package_text.lower()
    for marker in provider_markers:
        require(marker not in lower, f"provider SDK leakage into Quality Engine: {marker}")

    require("measured_width" in deterministic and "TEXT_OVERFLOW" in deterministic, "deterministic typography overflow grader missing")
    require("NODE_OUTSIDE_PARENT" in deterministic, "deterministic geometry grader missing")
    require("LOW_TEXT_CONTRAST" in deterministic, "deterministic contrast grader missing")
    require("EXPORT_RESOLUTION_TOO_LOW" in deterministic, "deterministic resolution gate missing")

    require("QUALITY_GRADER_VERSION_NOT_CALIBRATED" in calibration, "grader version calibration gate missing")
    require("QUALITY_GRADER_DATASET_VERSION_NOT_CALIBRATED" in calibration, "calibration dataset version gate missing")
    fixture = json.loads(read("fixtures/quality/node-50-calibration.json"))
    require(fixture.get("fixture_kind") == "SYNTHETIC_HUMAN_LABEL_STRUCTURE", "calibration fixture must not masquerade as production human study")
    require(len(fixture.get("samples", [])) >= 40, "calibration contract corpus is too small")

    require("overall_score / 100" in artifact, "Artifact quality score must convert 0-100 to historical 0-1 scale")
    require(".transition(" not in artifact, "Quality adapter must not approve/reject ArtifactVersion")
    require("content_hash" not in artifact or "content_hash" in read("packages/quality-engine/src/artifact-adapter.test.ts"), "Artifact content immutability evidence missing")

    for table in ["quality_profiles", "quality_grader_calibrations", "quality_results", "quality_dimension_results", "quality_violations", "quality_evidence"]:
        require(f"CREATE TABLE IF NOT EXISTS {table}" in migration, f"missing DB table {table}")
    require("NEW.overall_score / 100.0" in migration, "DB quality score normalization missing")
    require("UPDATE artifact_versions" in migration, "Artifact summary score sync missing")
    require("status IN ('PASS','PASS_WITH_WARNINGS','FAIL_REPAIRABLE','FAIL_HARD','REVIEW_REQUIRED')" in migration, "DB status domain mismatch")

    suite = json.loads(read("evals/datasets/visual-critic/suite.json"))
    cases = json.loads(read("evals/datasets/visual-critic/v1/cases.json"))["cases"]
    require(suite["name"] == "visual-critic", "NODE-05 suite name mismatch")
    require(len(cases) >= 8, "Visual Critic release-gate dataset needs at least 8 cases")

    for job in ["critic-contract", "critic-quality", "critic-integration", "critic-calibration", "critic-benchmark"]:
        require(f"{job}:" in workflow, f"missing CI job {job}")

    print("NODE-50 Visual Critic architecture validation: PASS")


if __name__ == "__main__":
    main()
