from __future__ import annotations

from uuid import UUID

import pytest

from lumi_api.brand_rules import (
    AssetRightsSnapshot,
    BrandAssetSet,
    BrandObservation,
    BrandRule,
    BrandRuleService,
    BrandToken,
    BrandTokenSet,
    BrandVoice,
    GuideCitation,
    InMemoryAssetRightsReader,
    InMemoryBrandRuleRepository,
    RuleKind,
    RuleSeverity,
    RuleSource,
    compile_brand_constraints,
)
from lumi_api.brand_rules.service import BrandRulePublicationDenied
from lumi_api.domain.ids import new_uuid7


ORG = UUID("11111111-1111-4111-8111-111111111111")
BRAND = UUID("22222222-2222-4222-8222-222222222222")
FONT = UUID("33333333-3333-4333-8333-333333333333")
LOGO = UUID("44444444-4444-4444-8444-444444444444")
GUIDE = UUID("55555555-5555-4555-8555-555555555555")
NODE = UUID("66666666-6666-4666-8666-666666666666")


def token_set(version=1):
    return BrandTokenSet(
        id=new_uuid7(),
        version=version,
        tokens=(
            BrandToken(id="color.primary", value="#FFCC00"),
            BrandToken(id="font.display", value=str(FONT)),
        ),
    )


def asset_set(version=1):
    return BrandAssetSet(
        id=new_uuid7(),
        version=version,
        allowed_logo_asset_ids=(LOGO,),
        allowed_font_asset_ids=(FONT,),
        reference_asset_ids=(GUIDE,),
    )


def rule(kind, severity=RuleSeverity.HARD, **params):
    return BrandRule(
        id=new_uuid7(),
        key=f"{kind.value.lower()}-{new_uuid7()}",
        kind=kind,
        severity=severity,
        source=RuleSource.MANUAL_ADMIN,
        parameters=params,
    )


def service():
    rights = InMemoryAssetRightsReader(
        (
            AssetRightsSnapshot(
                asset_id=FONT,
                exists=True,
                ready=True,
                media_kind="font",
                rights_level="owned",
                commercial_use=True,
            ),
        )
    )
    repo = InMemoryBrandRuleRepository()
    return BrandRuleService(repo, rights), repo, rights


def publish_basic(rules):
    svc, repo, rights = service()
    draft = svc.create_draft(
        organization_id=ORG,
        brand_id=BRAND,
        source=RuleSource.MANUAL_ADMIN,
        token_set=token_set(),
        asset_set=asset_set(),
        rules=rules,
        voice=BrandVoice(tone_attributes=("confident", "minimal")),
        created_by="admin",
    )
    published = svc.publish(
        organization_id=ORG,
        brand_id=BRAND,
        rule_set_id=draft.id,
        actor_id="admin",
    )
    return svc, repo, rights, published


def test_token_binding_and_context_snapshot():
    binding_rule = rule(
        RuleKind.TOKEN_BINDING,
        token_ids=["color.primary"],
        required=True,
    )
    svc, repo, rights, published = publish_basic((binding_rule,))
    context = svc.get_context(organization_id=ORG, brand_id=BRAND)
    assert context.rule_set_id == published.id
    assert context.rule_set_version == 1
    result = svc.compliance(
        organization_id=ORG,
        brand_id=BRAND,
        observations=(
            BrandObservation(
                node_id=NODE,
                kind="SHAPE",
                brand_binding="color.secondary",
            ),
        ),
    )
    assert not result.can_approve
    assert result.violations[0].code == "BRAND_TOKEN_BINDING_INVALID"


def test_forbidden_color_hard_blocks_approval():
    color_rule = rule(RuleKind.FORBIDDEN_COLOR, colors=["#ff0000"])
    svc, _, _, _ = publish_basic((color_rule,))
    result = svc.compliance(
        organization_id=ORG,
        brand_id=BRAND,
        observations=(BrandObservation(node_id=NODE, kind="SHAPE", color="#FF0000"),),
    )
    assert result.can_approve is False
    assert result.violations[0].severity == RuleSeverity.HARD


def test_logo_clear_space_and_transform():
    clear = rule(RuleKind.LOGO_CLEAR_SPACE, minimum=12)
    transform = rule(
        RuleKind.LOGO_TRANSFORM,
        forbid_rotation=True,
        forbid_stretch=True,
        forbid_recolor=True,
    )
    svc, _, _, _ = publish_basic((clear, transform))
    result = svc.compliance(
        organization_id=ORG,
        brand_id=BRAND,
        observations=(
            BrandObservation(
                node_id=NODE,
                kind="LOGO",
                asset_id=LOGO,
                clear_space=4,
                rotation_deg=8,
                scale_x=1,
                scale_y=1,
            ),
        ),
    )
    assert {item.code for item in result.violations} == {
        "BRAND_LOGO_CLEAR_SPACE",
        "BRAND_LOGO_ROTATED",
    }


def test_font_unavailable_is_not_silent_pass():
    font_rule = rule(RuleKind.FONT_ALLOWED, asset_ids=[str(FONT)])
    svc, _, rights, published = publish_basic((font_rule,))
    rights.put(
        AssetRightsSnapshot(
            asset_id=FONT,
            exists=False,
            ready=False,
            media_kind="font",
        )
    )
    result = svc.compliance(
        organization_id=ORG,
        brand_id=BRAND,
        rule_set_id=published.id,
        observations=(
            BrandObservation(
                node_id=NODE,
                kind="TEXT",
                font_asset_id=FONT,
                font_size=24,
            ),
        ),
    )
    assert not result.can_approve
    assert result.violations[0].unavailable is True
    assert result.violations[0].code == "BRAND_FONT_UNAVAILABLE"


def test_guide_extraction_requires_citation_and_human_review_before_hard_publish():
    svc, _, _ = service()
    inferred = BrandRule(
        id=new_uuid7(),
        key="logo-clear-space",
        kind=RuleKind.LOGO_CLEAR_SPACE,
        severity=RuleSeverity.HARD,
        source=RuleSource.INFERRED_PROPOSAL,
        parameters={"minimum": 16},
    )
    citation = GuideCitation(
        source_asset_id=GUIDE,
        page_number=7,
        chunk_ref="brand-guide:p7:block3",
        evidence_hash="a" * 64,
    )
    proposal = svc.create_guide_proposal(
        organization_id=ORG,
        brand_id=BRAND,
        source_asset_id=GUIDE,
        rules=(inferred,),
        citations=(citation,),
    )
    with pytest.raises(BrandRulePublicationDenied):
        svc.publish_guide_proposal(
            organization_id=ORG,
            brand_id=BRAND,
            proposal_id=proposal.id,
            token_set=token_set(),
            asset_set=asset_set(),
            voice=None,
            visual_style=None,
            actor_id="admin",
        )
    svc.review_guide_proposal(
        organization_id=ORG,
        brand_id=BRAND,
        proposal_id=proposal.id,
        actor_id="reviewer",
        approve=True,
    )
    published = svc.publish_guide_proposal(
        organization_id=ORG,
        brand_id=BRAND,
        proposal_id=proposal.id,
        token_set=token_set(),
        asset_set=asset_set(),
        voice=None,
        visual_style=None,
        actor_id="reviewer",
    )
    assert published.rules[0].source == RuleSource.APPROVED_GUIDE_EXTRACTION
    assert published.rules[0].severity == RuleSeverity.HARD


def test_version_snapshot_and_immutability():
    svc, repo, _, first = publish_basic((rule(RuleKind.FONT_MIN_SIZE, minimum=14),))
    second_draft = svc.create_draft(
        organization_id=ORG,
        brand_id=BRAND,
        source=RuleSource.USER_EXPLICIT,
        token_set=token_set(2),
        asset_set=asset_set(2),
        rules=(rule(RuleKind.FONT_MIN_SIZE, minimum=16),),
        created_by="user",
    )
    second = svc.publish(
        organization_id=ORG,
        brand_id=BRAND,
        rule_set_id=second_draft.id,
        actor_id="user",
    )
    assert first.version == 1
    assert second.version == 2
    assert first.snapshot_hash != second.snapshot_hash
    assert repo.get_rule_set(ORG, first.id) == first
    assert svc.get_context(organization_id=ORG, brand_id=BRAND).rule_set_id == second.id




def test_publication_denies_unverified_font_rights():
    svc, _, rights = service()
    rights.put(
        AssetRightsSnapshot(
            asset_id=FONT,
            exists=True,
            ready=True,
            media_kind="font",
            rights_level="restricted",
            commercial_use=False,
        )
    )
    draft = svc.create_draft(
        organization_id=ORG,
        brand_id=BRAND,
        source=RuleSource.MANUAL_ADMIN,
        token_set=token_set(),
        asset_set=asset_set(),
        rules=(rule(RuleKind.FONT_ALLOWED, asset_ids=[str(FONT)]),),
        created_by="admin",
    )
    with pytest.raises(BrandRulePublicationDenied):
        svc.publish(
            organization_id=ORG,
            brand_id=BRAND,
            rule_set_id=draft.id,
            actor_id="admin",
        )

def test_node14_constraint_bridge_preserves_hard_soft_and_published_version():
    contrast = rule(RuleKind.MIN_CONTRAST, severity=RuleSeverity.HARD, ratio=4.5)
    visual = rule(RuleKind.VISUAL_STYLE, severity=RuleSeverity.SOFT, style="editorial")
    _, _, _, published = publish_basic((contrast, visual))
    bundle = compile_brand_constraints(published)
    assert len(bundle.constraints) == 2
    assert bundle.constraints[0].source == "APPROVED_BRAND_RULE"
    assert {item.severity for item in bundle.constraints} == {"HARD", "SOFT"}
    assert all(
        item.parameters["brand_rule_set_version"] == published.version
        for item in bundle.constraints
    )
    assert all(item.scope.semantic_tags == () for item in bundle.constraints)
    assert bundle.constraints[0].parameters["min_ratio"] == 4.5
