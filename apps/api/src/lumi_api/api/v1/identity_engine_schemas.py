from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_api.identity_engine.contracts import (
    CalibrationSample,
    CandidateIdentity,
    IdentityType,
    ReferenceView,
    ThresholdProfile,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateIdentityReferenceSetRequest(ApiModel):
    project_id: UUID | None = None
    brand_id: UUID | None = None
    identity_type: IdentityType
    name: str = Field(min_length=1, max_length=240)
    canonical_asset_ids: tuple[UUID, ...]
    reference_views: tuple[ReferenceView, ...]
    threshold_profile: ThresholdProfile
    notes: str | None = Field(default=None, max_length=4000)
    privacy_authorized: bool = False


class CreateIdentityVersionRequest(ApiModel):
    canonical_asset_ids: tuple[UUID, ...]
    reference_views: tuple[ReferenceView, ...]
    threshold_profile: ThresholdProfile
    notes: str | None = Field(default=None, max_length=4000)


class ValidateIdentityRequest(ApiModel):
    candidate: CandidateIdentity
    threshold_profile: ThresholdProfile | None = None


class CalibrateIdentityRequest(ApiModel):
    identity_type: IdentityType
    profile_key: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    target_precision: float = Field(default=0.95, ge=0.5, le=1)
    samples: tuple[CalibrationSample, ...]


class CompareIdentityRequest(ApiModel):
    a: CandidateIdentity
    b: CandidateIdentity
    identity_type: IdentityType
    threshold_profile: ThresholdProfile
