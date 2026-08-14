from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "packages/brand-rules/src/types.ts",
    "packages/brand-rules/src/runtime.ts",
    "packages/brand-rules/src/context.ts",
    "packages/brand-rules/src/extraction.ts",
    "packages/brand-rules/src/constraint-adapter.ts",
    "packages/brand-rules/src/artifact-gate.ts",
    "packages/artifact-sdk/src/hashing.ts",
    "packages/artifact-sdk/src/export.ts",
    "services/brand-rules/src/lumi_brand_rules/model.py",
    "services/brand-rules/src/lumi_brand_rules/runtime.py",
    "services/artifact-history/src/lumi_artifacts/export_manifest.py",
    "db/migrations/0002_brand_rules.sql",
    "docs/runtime/BRAND-RULES-ENGINE-V1.md",
    "reports/nodes/NODE-43/acceptance.md",
)


def _read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise SystemExit(f"NODE-43 missing required file: {path}")
    return target.read_text(encoding="utf-8")


def _require(path: str, *needles: str) -> None:
    text = _read(path)
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"NODE-43 contract missing {needle!r} in {path}")


def main() -> None:
    for path in REQUIRED_FILES:
        _read(path)

    _require(
        "packages/brand-rules/src/runtime.ts",
        'rule.source === "INFERRED_PROPOSAL" && rule.severity === "HARD"',
        "evaluateBrandCompliance",
        "expected_document_version",
        "BRAND_LOGO_CLEAR_SPACE_VIOLATION",
        "BRAND_FONT_RIGHTS_UNAVAILABLE",
    )
    _require(
        "packages/brand-rules/src/context.ts",
        'ruleSet.status !== "PUBLISHED"',
        "pinned: true",
        "brand_rule_set_version",
    )
    _require(
        "packages/brand-rules/src/extraction.ts",
        'source: "INFERRED_PROPOSAL"',
        'source: "APPROVED_GUIDE_EXTRACTION"',
        "reviewer identity",
        "citations",
    )
    _require(
        "packages/brand-rules/src/constraint-adapter.ts",
        "BrandComplianceValidator",
        'reason_code: "VALIDATION_UNAVAILABLE"',
    )
    _require(
        "packages/brand-rules/src/artifact-gate.ts",
        "BRAND_RULE_VERSION_MISMATCH",
        "BRAND_HARD_VIOLATION",
    )
    _require(
        "packages/artifact-sdk/src/hashing.ts",
        "brand_rule_set_version",
        "brand rule set version mismatch between ArtifactVersion and provenance",
        "...(brandRuleSetVersion ? { brand_rule_set_version: brandRuleSetVersion } : {})",
    )
    _require(
        "packages/artifact-sdk/src/export.ts",
        "brand_rule_set_version: brandRuleSetVersion",
    )
    _require(
        "db/migrations/0002_brand_rules.sql",
        "brand_profiles",
        "brand_token_sets",
        "brand_asset_sets",
        "brand_rule_sets",
        "brand_rules",
        "brand_guide_extraction_proposals",
        "source = 'INFERRED_PROPOSAL' AND severity = 'HARD'",
        "brand_rule_set_version",
    )
    _require(
        "services/artifact-history/src/lumi_artifacts/model.py",
        "brand_rule_set_version: str | None = None",
        "self.brand_rule_set_version",
    )
    _require(
        "services/artifact-history/src/lumi_artifacts/export_manifest.py",
        '"brand_rule_set_version"',
        "brand rule set version mismatch between version and provenance",
    )
    print("NODE-43 Brand Rules Engine contract validation: OK")


if __name__ == "__main__":
    main()
