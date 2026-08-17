from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from lumi_api.brand_rules.contracts import (
    BrandAssetSet,
    BrandObservation,
    BrandRule,
    BrandTokenSet,
    BrandVisualStyle,
    BrandVoice,
    GuideCitation,
    RuleSource,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateBrandRuleSetRequest(ApiModel):
    source: RuleSource
    token_set: BrandTokenSet
    asset_set: BrandAssetSet
    rules: tuple[BrandRule, ...]
    voice: BrandVoice = BrandVoice()
    visual_style: BrandVisualStyle = BrandVisualStyle()


class BrandComplianceRequest(ApiModel):
    rule_set_id: UUID | None = None
    observations: tuple[BrandObservation, ...]


class CreateGuideProposalRequest(ApiModel):
    source_asset_id: UUID
    rules: tuple[BrandRule, ...]
    citations: tuple[GuideCitation, ...]


class ReviewGuideProposalRequest(ApiModel):
    approve: bool


class PublishGuideProposalRequest(ApiModel):
    token_set: BrandTokenSet
    asset_set: BrandAssetSet
    voice: BrandVoice = BrandVoice()
    visual_style: BrandVisualStyle = BrandVisualStyle()
