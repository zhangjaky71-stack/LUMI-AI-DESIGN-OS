from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256 = r"^[0-9a-f]{64}$"


class BrandModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RuleSeverity(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    ADVISORY = "ADVISORY"


class RuleSource(StrEnum):
    USER_EXPLICIT = "USER_EXPLICIT"
    APPROVED_GUIDE_EXTRACTION = "APPROVED_GUIDE_EXTRACTION"
    MANUAL_ADMIN = "MANUAL_ADMIN"
    INFERRED_PROPOSAL = "INFERRED_PROPOSAL"


class RuleSetStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class ProposalStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


class RuleKind(StrEnum):
    TOKEN_BINDING = "TOKEN_BINDING"
    ALLOWED_COLOR = "ALLOWED_COLOR"
    FORBIDDEN_COLOR = "FORBIDDEN_COLOR"
    MIN_CONTRAST = "MIN_CONTRAST"
    FONT_ALLOWED = "FONT_ALLOWED"
    FONT_MIN_SIZE = "FONT_MIN_SIZE"
    LOGO_ALLOWED_ASSET = "LOGO_ALLOWED_ASSET"
    LOGO_MIN_SIZE = "LOGO_MIN_SIZE"
    LOGO_CLEAR_SPACE = "LOGO_CLEAR_SPACE"
    LOGO_TRANSFORM = "LOGO_TRANSFORM"
    COPY_VOCABULARY = "COPY_VOCABULARY"
    VISUAL_STYLE = "VISUAL_STYLE"


class BrandToken(BrandModel):
    id: str = Field(min_length=3, max_length=160)
    value: str = Field(min_length=1, max_length=500)
    profile: str | None = Field(default=None, max_length=80)


class BrandTokenSet(BrandModel):
    id: UUID
    version: int = Field(ge=1)
    tokens: tuple[BrandToken, ...] = Field(default=(), max_length=2_000)

    @model_validator(mode="after")
    def unique_tokens(self) -> "BrandTokenSet":
        ids = [item.id for item in self.tokens]
        if len(ids) != len(set(ids)):
            raise ValueError("brand token ids must be unique")
        return self


class BrandAssetSet(BrandModel):
    id: UUID
    version: int = Field(ge=1)
    allowed_logo_asset_ids: tuple[UUID, ...] = ()
    allowed_font_asset_ids: tuple[UUID, ...] = ()
    reference_asset_ids: tuple[UUID, ...] = ()
    negative_reference_asset_ids: tuple[UUID, ...] = ()

    @field_validator(
        "allowed_logo_asset_ids",
        "allowed_font_asset_ids",
        "reference_asset_ids",
        "negative_reference_asset_ids",
    )
    @classmethod
    def unique_assets(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("brand asset ids must be unique")
        return tuple(sorted(value, key=str))


class BrandVoice(BrandModel):
    tone_attributes: tuple[str, ...] = ()
    preferred_vocabulary: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    do_examples: tuple[str, ...] = ()
    dont_examples: tuple[str, ...] = ()
    locale_notes: tuple[tuple[str, str], ...] = ()


class BrandVisualStyle(BrandModel):
    photography_direction: tuple[str, ...] = ()
    lighting: tuple[str, ...] = ()
    composition: tuple[str, ...] = ()
    background_style: tuple[str, ...] = ()
    texture: tuple[str, ...] = ()
    illustration_style: tuple[str, ...] = ()


class BrandRule(BrandModel):
    id: UUID
    key: str = Field(min_length=3, max_length=160)
    kind: RuleKind
    severity: RuleSeverity
    source: RuleSource
    parameters: dict[str, Any] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=1_000)

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("brand rule id must be UUIDv7")
        return value


class GuideCitation(BrandModel):
    source_asset_id: UUID
    page_number: int = Field(ge=1, le=100_000)
    chunk_ref: str = Field(min_length=1, max_length=500)
    evidence_hash: str = Field(pattern=_SHA256)


class BrandGuideProposal(BrandModel):
    id: UUID
    organization_id: UUID
    brand_id: UUID
    source_asset_id: UUID
    status: ProposalStatus = ProposalStatus.PENDING_REVIEW
    rules: tuple[BrandRule, ...]
    citations: tuple[GuideCitation, ...]
    created_at: datetime
    reviewed_by: str | None = Field(default=None, max_length=200)
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def proposal_is_cited_and_inferred(self) -> "BrandGuideProposal":
        if not self.citations:
            raise ValueError("guide extraction proposal requires source citations")
        if any(item.source_asset_id != self.source_asset_id for item in self.citations):
            raise ValueError("citation source asset must match proposal source asset")
        if any(item.source != RuleSource.INFERRED_PROPOSAL for item in self.rules):
            raise ValueError("unreviewed guide proposal rules must be INFERRED_PROPOSAL")
        return self


class BrandRuleSet(BrandModel):
    id: UUID
    organization_id: UUID
    brand_id: UUID
    version: int = Field(ge=1)
    status: RuleSetStatus
    source: RuleSource
    token_set: BrandTokenSet
    asset_set: BrandAssetSet
    rules: tuple[BrandRule, ...]
    voice: BrandVoice = BrandVoice()
    visual_style: BrandVisualStyle = BrandVisualStyle()
    source_proposal_id: UUID | None = None
    created_by: str = Field(min_length=1, max_length=200)
    created_at: datetime
    published_at: datetime | None = None
    published_by: str | None = Field(default=None, max_length=200)
    snapshot_hash: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_ruleset(self) -> "BrandRuleSet":
        ids = [rule.id for rule in self.rules]
        keys = [rule.key for rule in self.rules]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("brand rule ids and keys must be unique")
        if self.status == RuleSetStatus.PUBLISHED and (
            self.published_at is None or self.published_by is None
        ):
            raise ValueError("published rule set requires published_at and published_by")
        if self.status != RuleSetStatus.PUBLISHED and (
            self.published_at is not None or self.published_by is not None
        ):
            raise ValueError("non-published rule set cannot carry publish audit fields")
        if self.status == RuleSetStatus.PUBLISHED and self.source == RuleSource.INFERRED_PROPOSAL:
            raise ValueError("inferred proposal cannot be published without human approval")
        return self


class BrandContext(BrandModel):
    brand_id: UUID
    rule_set_id: UUID
    rule_set_version: int
    snapshot_hash: str = Field(pattern=_SHA256)
    hard_rules: tuple[BrandRule, ...]
    selected_tokens: tuple[BrandToken, ...]
    allowed_logo_asset_ids: tuple[UUID, ...]
    allowed_font_asset_ids: tuple[UUID, ...]
    voice_summary: tuple[str, ...]
    reference_asset_ids: tuple[UUID, ...]


class BrandObservation(BrandModel):
    node_id: UUID | None = None
    kind: str = Field(min_length=1, max_length=80)
    brand_binding: str | None = Field(default=None, max_length=160)
    color: str | None = Field(default=None, max_length=64)
    font_asset_id: UUID | None = None
    font_family: str | None = Field(default=None, max_length=200)
    font_size: float | None = Field(default=None, ge=0)
    asset_id: UUID | None = None
    width: float | None = Field(default=None, ge=0)
    height: float | None = Field(default=None, ge=0)
    clear_space: float | None = Field(default=None, ge=0)
    rotation_deg: float | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    recolored: bool | None = None
    background_class: str | None = Field(default=None, max_length=80)
    contrast_ratio: float | None = Field(default=None, ge=0)


class BrandViolation(BrandModel):
    rule_id: UUID
    rule_key: str
    severity: RuleSeverity
    node_id: UUID | None = None
    code: str = Field(min_length=1, max_length=160)
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    unavailable: bool = False

    @property
    def blocking(self) -> bool:
        return self.severity == RuleSeverity.HARD


class ComplianceResult(BrandModel):
    rule_set_id: UUID
    rule_set_version: int
    violations: tuple[BrandViolation, ...]
    score: float = Field(ge=0, le=100)
    can_approve: bool


class AssetRightsSnapshot(BrandModel):
    asset_id: UUID
    exists: bool
    ready: bool
    media_kind: str | None = None
    rights_level: str | None = None
    commercial_use: bool | None = None


def canonical_snapshot_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
