from __future__ import annotations

import pytest

from lumi_brand_rules import (
    BrandAssetSet,
    BrandRule,
    BrandRuleError,
    BrandRuleSet,
    BrandTokenSet,
    ExtractionCandidate,
    approve_extraction_proposal,
    build_brand_context,
    create_extraction_proposal,
    evaluate_brand_compliance,
    publish_rule_set,
    validate_rule_set,
)


def _rule(
    rule_id: str,
    rule_type: str,
    *,
    category: str,
    severity: str = "HARD",
    scope: dict[str, object] | None = None,
    parameters: dict[str, object] | None = None,
) -> BrandRule:
    return BrandRule(
        id=rule_id,
        category=category,
        type=rule_type,
        severity=severity,  # type: ignore[arg-type]
        source="MANUAL_ADMIN",
        priority=100,
        scope=scope or {},
        parameters=parameters or {},
    )


def _published() -> tuple[BrandRuleSet, BrandTokenSet, BrandAssetSet]:
    rules = (
        _rule(
            "color",
            "FORBIDDEN_COLORS",
            category="COLOR",
            scope={"roles": ["headline"]},
            parameters={"colors": ["#ff0000"]},
        ),
        _rule(
            "font",
            "ALLOWED_FONT_ASSETS",
            category="TYPOGRAPHY",
            scope={"roles": ["headline"]},
            parameters={"asset_ids": ["font-good"]},
        ),
        _rule(
            "logo",
            "LOGO_FORBID_ROTATION",
            category="LOGO",
            scope={"roles": ["logo"]},
        ),
        _rule(
            "clear",
            "LOGO_CLEAR_SPACE",
            category="LOGO",
            scope={"roles": ["logo"]},
            parameters={"px": 4},
        ),
    )
    rule_set = publish_rule_set(
        BrandRuleSet(
            id="rules-1",
            organization_id="org-1",
            brand_profile_id="brand-1",
            version="1.0.0",
            status="DRAFT",
            token_set_version="1.0.0",
            asset_set_version="1.0.0",
            rules=rules,
            voice={"forbidden_terms": ["cheap"]},
        )
    )
    tokens = BrandTokenSet(
        brand_profile_id="brand-1",
        version="1.0.0",
        colors={"primary": "#111111"},
        font_asset_ids=("font-good",),
        spacing_scale=(4, 8, 12),
    )
    assets = BrandAssetSet(
        brand_profile_id="brand-1",
        version="1.0.0",
        logo_asset_ids=("logo-a",),
        font_asset_ids=("font-good",),
        reference_asset_ids=("ref-a",),
    )
    return rule_set, tokens, assets


def _document() -> dict[str, object]:
    return {
        "metadata": {"document_version": 4},
        "nodes": {
            "root": {
                "id": "root",
                "kind": "DOCUMENT_ROOT",
                "parent_id": None,
                "children": ["logo", "title", "shape"],
            },
            "logo": {
                "id": "logo",
                "kind": "IMAGE",
                "role": "logo",
                "asset_id": "logo-a",
                "transform": {"x": 0, "y": 0, "width": 20, "height": 10, "rotation_deg": 5},
            },
            "title": {
                "id": "title",
                "kind": "TEXT",
                "role": "headline",
                "fill": "#ff0000",
                "font_asset_id": "font-bad",
                "text": "Cheap forever",
            },
            "shape": {
                "id": "shape",
                "kind": "SHAPE",
                "transform": {"x": 22, "y": 0, "width": 20, "height": 10},
            },
        },
    }


def test_deterministic_compliance_fails_on_hard_brand_violations() -> None:
    rule_set, tokens, assets = _published()
    report = evaluate_brand_compliance(
        _document(),
        rule_set,
        tokens,
        assets,
        verified_asset_ids=frozenset({"logo-a", "font-good"}),
        font_rights_allowed_asset_ids=frozenset({"font-good"}),
    )
    assert report.decision == "FAIL"
    assert report.hard_violation_count >= 4
    codes = {item.reason_code for item in report.diagnostics}
    assert "BRAND_COLOR_FORBIDDEN" in codes
    assert "BRAND_FONT_NOT_ALLOWED" in codes
    assert "BRAND_LOGO_ROTATED" in codes
    assert "BRAND_LOGO_CLEAR_SPACE_VIOLATION" in codes
    color = next(item for item in report.diagnostics if item.rule_id == "color")
    assert color.repair_operations[0]["type"] == "SET_PROPERTY"


def test_brand_context_is_pinned_and_version_exact() -> None:
    rule_set, tokens, assets = _published()
    context = build_brand_context(rule_set, tokens, assets)
    assert context["pinned"] is True
    assert context["brand_rule_set_version"] == "1.0.0"
    assert "logo" in context["hard_rule_ids"]


def test_inferred_hard_is_rejected() -> None:
    rule_set, _, _ = _published()
    bad = BrandRule(
        id="bad",
        category="LOGO",
        type="LOGO_CLEAR_SPACE",
        severity="HARD",
        source="INFERRED_PROPOSAL",
        priority=1,
    )
    with pytest.raises(BrandRuleError, match="cannot be HARD"):
        validate_rule_set(
            BrandRuleSet(
                id="draft",
                organization_id="org-1",
                brand_profile_id="brand-1",
                version="2.0.0",
                status="DRAFT",
                token_set_version=rule_set.token_set_version,
                asset_set_version=rule_set.asset_set_version,
                rules=(bad,),
            )
        )


def test_extraction_requires_citations_and_human_approval_for_hard() -> None:
    candidate_rule = BrandRule(
        id="extracted-clear-space",
        category="LOGO",
        type="LOGO_CLEAR_SPACE",
        severity="SOFT",
        source="INFERRED_PROPOSAL",
        priority=50,
        parameters={"px": 8},
    )
    candidate = ExtractionCandidate(
        candidate_id="candidate-1",
        rule=candidate_rule,
        confidence=0.92,
        citations=({"source_asset_id": "guide", "page": 3, "span": "clear space"},),
    )
    proposal = create_extraction_proposal(
        proposal_id="proposal-1",
        organization_id="org-1",
        brand_profile_id="brand-1",
        source_asset_id="guide",
        created_at="2026-08-14T00:00:00Z",
        candidates=(candidate,),
    )
    approved, rule = approve_extraction_proposal(
        proposal,
        candidate_id="candidate-1",
        reviewer="reviewer-1",
        reviewed_at="2026-08-14T00:01:00Z",
        severity="HARD",
    )
    assert approved.status == "APPROVED"
    assert rule.source == "APPROVED_GUIDE_EXTRACTION"
    assert rule.severity == "HARD"
    assert rule.citations[0]["page"] == 3


def test_stale_brand_dependency_version_fails_closed() -> None:
    rule_set, tokens, assets = _published()
    stale = BrandTokenSet(
        brand_profile_id=tokens.brand_profile_id,
        version="2.0.0",
        colors=tokens.colors,
        font_asset_ids=tokens.font_asset_ids,
        spacing_scale=tokens.spacing_scale,
    )
    with pytest.raises(BrandRuleError, match="version mismatch"):
        evaluate_brand_compliance(_document(), rule_set, stale, assets)
