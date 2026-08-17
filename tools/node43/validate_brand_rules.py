from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(path: str, *markers: str) -> None:
    value = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in value:
            raise AssertionError(f"{path}: missing marker {marker!r}")


def main() -> None:
    require(
        "apps/api/src/lumi_api/brand_rules/contracts.py",
        "class BrandRuleSet",
        "class BrandGuideProposal",
        "class BrandContext",
        "INFERRED_PROPOSAL",
        "published_by",
    )
    require(
        "apps/api/src/lumi_api/brand_rules/service.py",
        "human-approved guide proposal is required",
        "_validate_asset_rights",
        "RuleSource.APPROVED_GUIDE_EXTRACTION",
    )
    require(
        "apps/api/src/lumi_api/brand_rules/compliance.py",
        "BRAND_FORBIDDEN_COLOR",
        "BRAND_LOGO_CLEAR_SPACE",
        "BRAND_FONT_UNAVAILABLE",
        "can_approve",
    )
    require(
        "apps/api/src/lumi_api/brand_rules/constraint_adapter.py",
        'source="APPROVED_BRAND_RULE"',
        '"REQUIRE_CONTRAST"',
        '"REQUIRE_TEXT_READABILITY"',
        '"REQUIRE_BRAND_COMPLIANCE"',
        "ConstraintScope()",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/context_engine/brand_source.py",
        "BrandContextRetrievalSource",
        "ContextKind.BRAND_RULE",
        "TrustLevel.TRUSTED_PROJECT_DATA",
        "required=True",
        "pinned=True",
    )
    require(
        "apps/api/migrations/versions/20260817_0012_brand_rules_engine.py",
        'revision = "20260817_0012"',
        'down_revision = "20260817_0011"',
    )
    require(
        "apps/api/migrations/versions/20260817_0012_sql/up_01.sql",
        "brand_rule_version_counters",
        "brand_rule_set_versions",
        "brand_guide_proposals",
        "lumi_brand_rules_immutable_snapshot",
        "INFERRED_PROPOSAL",
    )
    require(
        "apps/api/migrations/versions/20260817_0012_sql/up_02.sql",
        "brand_rule_set_version_id",
        "lumi_validate_active_brand_rule_set",
        "lumi_capture_artifact_brand_rule_set",
        "lumi_capture_agent_run_brand_rule_set",
    )
    require(
        "apps/api/src/lumi_api/api/v1/brand_rules_routes.py",
        "/brands/{brand_id}/rule-sets",
        "/brands/{brand_id}/context",
        "/brands/{brand_id}/compliance",
        "/guide-proposals/{proposal_id}/review",
        "/guide-proposals/{proposal_id}/publish",
        "_actor_id",
    )
    require(
        "apps/api/src/lumi_api/api/v1/app.py",
        "brand_rules_router",
    )
    fixture = json.loads(
        (ROOT / "evals/node43/brand-rule-fixtures.json").read_text(encoding="utf-8")
    )
    assert fixture["schema"] == "lumi.node43-brand-eval/1.0"
    assert len(fixture["cases"]) >= 20

    ledger = json.loads(
        (ROOT / "reports/nodes/NODE-43/gap-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["node"] == "NODE-43"
    assert len(ledger["gaps"]) == 5
    assert len({item["id"] for item in ledger["gaps"]}) == 5

    routes = (
        ROOT / "apps/api/src/lumi_api/api/v1/brand_rules_routes.py"
    ).read_text(encoding="utf-8")
    required_endpoints = (
        "rule-sets",
        "publish_rule_set",
        "get_brand_context",
        "evaluate_brand_compliance",
        "create_guide_proposal",
        "review_guide_proposal",
        "publish_guide_proposal",
    )
    for marker in required_endpoints:
        assert marker in routes
    assert "body.rule_set_id" not in routes
    assert "rule_set_id=rule_set_id" in routes

    print("NODE43_BRAND_RULES_VALIDATION_PASS")
    print(f"fixture_cases={len(fixture['cases'])}")
    print(f"required_endpoints={len(required_endpoints)}")
    print(f"production_gaps={len(ledger['gaps'])}")


if __name__ == "__main__":
    main()
