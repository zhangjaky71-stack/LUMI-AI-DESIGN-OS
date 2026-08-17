from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class IdentityType(StrEnum):
    PRODUCT = "PRODUCT"
    LOGO = "LOGO"
    CHARACTER = "CHARACTER"
    FACE = "FACE"
    STYLE_REFERENCE = "STYLE_REFERENCE"


class IdentitySeverity(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    ADVISORY = "ADVISORY"


class UnavailablePolicy(StrEnum):
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    WARN = "WARN"


class IdentityStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCKED = "BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VALIDATION_UNAVAILABLE = "VALIDATION_UNAVAILABLE"


class SignalName(StrEnum):
    EXACT_HASH = "EXACT_HASH"
    PERCEPTUAL = "PERCEPTUAL"
    FEATURE_MATCH = "FEATURE_MATCH"
    OCR_WORDMARK = "OCR_WORDMARK"
    MULTIMODAL_EMBEDDING = "MULTIMODAL_EMBEDDING"
    LOCAL_FEATURE = "LOCAL_FEATURE"
    SHAPE_COLOR = "SHAPE_COLOR"
    BRAND_REGION = "BRAND_REGION"
    VLM_STRUCTURED = "VLM_STRUCTURED"


class SampleLabel(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEAR_MISS = "NEAR_MISS"


class RegionEvidence(IdentityModel):
    source: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    detection_confidence: float = Field(ge=0, le=1)
    quality: float = Field(ge=0, le=1)
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def within_canvas(self) -> RegionEvidence:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("IDENTITY_REGION_OUT_OF_BOUNDS")
        return self


class ThresholdProfile(IdentityModel):
    profile_key: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    scenario: str = Field(min_length=1, max_length=120)
    severity: IdentitySeverity
    min_score: float = Field(ge=0, le=100)
    min_confidence: float = Field(ge=0, le=1)
    min_signal_count: int = Field(ge=1, le=9)
    unavailable_policy: UnavailablePolicy
    calibration_report_id: UUID | None = None


class ReferenceView(IdentityModel):
    asset_id: UUID
    view_key: str = Field(min_length=1, max_length=120)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class IdentityReferenceSet(IdentityModel):
    id: UUID
    organization_id: UUID
    project_id: UUID | None = None
    brand_id: UUID | None = None
    identity_type: IdentityType
    name: str = Field(min_length=1, max_length=240)
    canonical_asset_ids: tuple[UUID, ...] = Field(min_length=1, max_length=64)
    reference_views: tuple[ReferenceView, ...] = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=4000)
    threshold_profile: ThresholdProfile
    version: int = Field(ge=1)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    created_by: str = Field(min_length=1, max_length=200)
    privacy_authorized: bool = False

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("IDENTITY_TIMESTAMP_TZ_REQUIRED")
        return value

    @model_validator(mode="after")
    def reference_integrity(self) -> IdentityReferenceSet:
        if len(self.canonical_asset_ids) != len(set(self.canonical_asset_ids)):
            raise ValueError("IDENTITY_CANONICAL_ASSET_DUPLICATE")
        view_keys = [view.view_key for view in self.reference_views]
        if len(view_keys) != len(set(view_keys)):
            raise ValueError("IDENTITY_REFERENCE_VIEW_DUPLICATE")
        canonical = set(self.canonical_asset_ids)
        if any(view.asset_id not in canonical for view in self.reference_views):
            raise ValueError("IDENTITY_REFERENCE_VIEW_ASSET_NOT_CANONICAL")
        return self

    @model_validator(mode="after")
    def privacy_scope(self) -> IdentityReferenceSet:
        if self.identity_type is IdentityType.FACE:
            if not self.privacy_authorized or self.project_id is None:
                raise ValueError("IDENTITY_FACE_PROJECT_AUTH_REQUIRED")
            if self.brand_id is not None:
                raise ValueError("IDENTITY_FACE_BRAND_SCOPE_FORBIDDEN")
        return self


class CandidateIdentity(IdentityModel):
    asset_id: UUID | None = None
    node_id: str | None = Field(default=None, max_length=200)
    declared_region: RegionEvidence | None = None
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def has_target(self) -> CandidateIdentity:
        if self.asset_id is None and self.node_id is None:
            raise ValueError("IDENTITY_CANDIDATE_TARGET_REQUIRED")
        return self


class SignalScore(IdentityModel):
    name: SignalName
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    available: bool = True
    evidence_refs: tuple[str, ...] = ()
    detail: Mapping[str, Any] = Field(default_factory=dict)


class SignalBundle(IdentityModel):
    region: RegionEvidence | None
    signals: tuple[SignalScore, ...]
    provider_version: str = Field(min_length=1, max_length=160)
    evidence_refs: tuple[str, ...] = ()


class IdentityValidationResult(IdentityModel):
    identity_id: UUID
    reference_version: int
    reference_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_type: IdentityType
    status: IdentityStatus
    identity_score: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    threshold_profile: ThresholdProfile
    signal_scores: tuple[SignalScore, ...]
    region: RegionEvidence | None
    evidence_refs: tuple[str, ...]
    failure_codes: tuple[str, ...] = ()
    provider_version: str | None = None
    candidate_asset_id: UUID | None = None
    candidate_node_id: str | None = Field(default=None, max_length=200)

    @property
    def score_01(self) -> float | None:
        if self.identity_score is None:
            return None
        return self.identity_score / 100.0


class CalibrationSample(IdentityModel):
    sample_id: str = Field(min_length=1, max_length=160)
    identity_type: IdentityType
    scenario: str = Field(min_length=1, max_length=120)
    label: SampleLabel
    signal_scores: tuple[SignalScore, ...] = Field(min_length=1)
    crop_quality: float = Field(default=1.0, ge=0, le=1)


class CalibrationMetrics(IdentityModel):
    threshold: float = Field(ge=0, le=100)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    false_accept_rate: float = Field(ge=0, le=1)
    false_reject_rate: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    positives: int = Field(ge=0)
    negatives: int = Field(ge=0)


class CalibrationReport(IdentityModel):
    id: UUID
    organization_id: UUID
    identity_type: IdentityType
    profile_key: str
    version: int = Field(ge=1)
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_threshold: float = Field(ge=0, le=100)
    target_precision: float = Field(ge=0, le=1)
    metrics: CalibrationMetrics
    sample_count: int = Field(ge=1)
    created_at: datetime


def canonical_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
