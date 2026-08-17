from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .compliance import evaluate_compliance
from .contracts import (
    BrandAssetSet,
    BrandContext,
    BrandGuideProposal,
    BrandObservation,
    BrandRule,
    BrandRuleSet,
    BrandTokenSet,
    BrandVisualStyle,
    BrandVoice,
    ComplianceResult,
    GuideCitation,
    ProposalStatus,
    RuleSetStatus,
    RuleSource,
    canonical_snapshot_hash,
)
from .ports import AssetRightsReader, BrandRuleRepository


class BrandRuleError(RuntimeError):
    code = "brand_rule_error"


class BrandRuleNotFound(BrandRuleError):
    code = "brand_rule_not_found"


class BrandRuleConflict(BrandRuleError):
    code = "brand_rule_conflict"


class BrandRulePublicationDenied(BrandRuleError):
    code = "brand_rule_publication_denied"


class BrandRuleService:
    def __init__(
        self,
        repository: BrandRuleRepository,
        rights_reader: AssetRightsReader | None = None,
    ) -> None:
        self.repository = repository
        self.rights_reader = rights_reader

    def create_draft(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        source: RuleSource,
        token_set: BrandTokenSet,
        asset_set: BrandAssetSet,
        rules: tuple[BrandRule, ...],
        voice: BrandVoice | None = None,
        visual_style: BrandVisualStyle | None = None,
        created_by: str,
        source_proposal_id: UUID | None = None,
    ) -> BrandRuleSet:
        if source == RuleSource.INFERRED_PROPOSAL:
            raise BrandRulePublicationDenied(
                "inferred rules must enter through a cited guide proposal"
            )
        now = datetime.now(timezone.utc)
        version = self.repository.next_version(organization_id, brand_id)
        payload = {
            "organization_id": str(organization_id),
            "brand_id": str(brand_id),
            "version": version,
            "source": source.value,
            "token_set": token_set.model_dump(mode="json"),
            "asset_set": asset_set.model_dump(mode="json"),
            "rules": [item.model_dump(mode="json") for item in rules],
            "voice": (voice or BrandVoice()).model_dump(mode="json"),
            "visual_style": (visual_style or BrandVisualStyle()).model_dump(mode="json"),
            "source_proposal_id": str(source_proposal_id) if source_proposal_id else None,
        }
        value = BrandRuleSet(
            id=new_uuid7(),
            organization_id=organization_id,
            brand_id=brand_id,
            version=version,
            status=RuleSetStatus.DRAFT,
            source=source,
            token_set=token_set,
            asset_set=asset_set,
            rules=rules,
            voice=voice or BrandVoice(),
            visual_style=visual_style or BrandVisualStyle(),
            source_proposal_id=source_proposal_id,
            created_by=created_by,
            created_at=now,
            snapshot_hash=canonical_snapshot_hash(payload),
        )
        self.repository.save_rule_set(value)
        return value

    def publish(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        rule_set_id: UUID,
        actor_id: str,
    ) -> BrandRuleSet:
        current = self.repository.get_rule_set(organization_id, rule_set_id)
        if current is None or current.brand_id != brand_id:
            raise BrandRuleNotFound("brand rule set not found")
        if current.status != RuleSetStatus.DRAFT:
            raise BrandRuleConflict("only DRAFT brand rule set may be published")
        if current.source == RuleSource.INFERRED_PROPOSAL:
            raise BrandRulePublicationDenied(
                "INFERRED_PROPOSAL cannot become published without review"
            )
        self._validate_asset_rights(organization_id, current)
        published = current.model_copy(
            update={
                "status": RuleSetStatus.PUBLISHED,
                "published_at": datetime.now(timezone.utc),
                "published_by": actor_id,
            }
        )
        self.repository.save_rule_set(published)
        self.repository.set_active_rule_set(organization_id, brand_id, published.id)
        return published

    def create_guide_proposal(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        source_asset_id: UUID,
        rules: tuple[BrandRule, ...],
        citations: tuple[GuideCitation, ...],
    ) -> BrandGuideProposal:
        now = datetime.now(timezone.utc)
        proposal = BrandGuideProposal(
            id=new_uuid7(),
            organization_id=organization_id,
            brand_id=brand_id,
            source_asset_id=source_asset_id,
            rules=rules,
            citations=citations,
            created_at=now,
        )
        self.repository.save_proposal(proposal)
        return proposal

    def review_guide_proposal(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        proposal_id: UUID,
        actor_id: str,
        approve: bool,
    ) -> BrandGuideProposal:
        current = self.repository.get_proposal(organization_id, proposal_id)
        if current is None or current.brand_id != brand_id:
            raise BrandRuleNotFound("brand guide proposal not found")
        if current.status != ProposalStatus.PENDING_REVIEW:
            raise BrandRuleConflict("proposal is not pending review")
        reviewed = current.model_copy(
            update={
                "status": ProposalStatus.APPROVED if approve else ProposalStatus.REJECTED,
                "reviewed_by": actor_id,
                "reviewed_at": datetime.now(timezone.utc),
            }
        )
        self.repository.save_proposal(reviewed)
        return reviewed

    def publish_guide_proposal(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        proposal_id: UUID,
        token_set: BrandTokenSet,
        asset_set: BrandAssetSet,
        voice: BrandVoice | None,
        visual_style: BrandVisualStyle | None,
        actor_id: str,
    ) -> BrandRuleSet:
        proposal = self.repository.get_proposal(organization_id, proposal_id)
        if proposal is None or proposal.brand_id != brand_id:
            raise BrandRuleNotFound("brand guide proposal not found")
        if proposal.status != ProposalStatus.APPROVED or not proposal.reviewed_by:
            raise BrandRulePublicationDenied(
                "human-approved guide proposal is required before publication"
            )
        approved_rules = tuple(
            item.model_copy(update={"source": RuleSource.APPROVED_GUIDE_EXTRACTION})
            for item in proposal.rules
        )
        draft = self.create_draft(
            organization_id=organization_id,
            brand_id=proposal.brand_id,
            source=RuleSource.APPROVED_GUIDE_EXTRACTION,
            token_set=token_set,
            asset_set=asset_set,
            rules=approved_rules,
            voice=voice,
            visual_style=visual_style,
            created_by=actor_id,
            source_proposal_id=proposal.id,
        )
        published = self.publish(
            organization_id=organization_id,
            brand_id=proposal.brand_id,
            rule_set_id=draft.id,
            actor_id=actor_id,
        )
        self.repository.save_proposal(
            proposal.model_copy(update={"status": ProposalStatus.PUBLISHED})
        )
        return published

    def get_context(
        self, *, organization_id: UUID, brand_id: UUID
    ) -> BrandContext:
        rule_set = self.repository.get_active_rule_set(organization_id, brand_id)
        if rule_set is None:
            raise BrandRuleNotFound("active brand rule set not found")
        return BrandContext(
            brand_id=brand_id,
            rule_set_id=rule_set.id,
            rule_set_version=rule_set.version,
            snapshot_hash=rule_set.snapshot_hash,
            hard_rules=tuple(
                item for item in rule_set.rules if item.severity.value == "HARD"
            ),
            selected_tokens=rule_set.token_set.tokens,
            allowed_logo_asset_ids=rule_set.asset_set.allowed_logo_asset_ids,
            allowed_font_asset_ids=rule_set.asset_set.allowed_font_asset_ids,
            voice_summary=rule_set.voice.tone_attributes
            + rule_set.voice.preferred_vocabulary[:8],
            reference_asset_ids=rule_set.asset_set.reference_asset_ids,
        )

    def compliance(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        observations: tuple[BrandObservation, ...],
        rule_set_id: UUID | None = None,
    ) -> ComplianceResult:
        if rule_set_id is None:
            rule_set = self.repository.get_active_rule_set(organization_id, brand_id)
        else:
            rule_set = self.repository.get_rule_set(organization_id, rule_set_id)
        if rule_set is None or rule_set.brand_id != brand_id:
            raise BrandRuleNotFound("brand rule set not found")
        return evaluate_compliance(
            organization_id,
            rule_set,
            observations,
            rights=self.rights_reader,
        )

    def _validate_asset_rights(
        self, organization_id: UUID, rule_set: BrandRuleSet
    ) -> None:
        if self.rights_reader is None:
            if rule_set.asset_set.allowed_font_asset_ids:
                raise BrandRulePublicationDenied(
                    "font asset rights reader unavailable for publication"
                )
            return
        for asset_id in rule_set.asset_set.allowed_font_asset_ids:
            state = self.rights_reader.read(organization_id, asset_id)
            if not state.exists or not state.ready or state.media_kind != "font":
                raise BrandRulePublicationDenied(
                    f"brand font asset unavailable: {asset_id}"
                )
            if state.commercial_use is False:
                raise BrandRulePublicationDenied(
                    f"brand font rights deny commercial use: {asset_id}"
                )
