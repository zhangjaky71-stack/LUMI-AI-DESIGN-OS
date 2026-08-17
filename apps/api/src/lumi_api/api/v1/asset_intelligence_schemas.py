from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_asset_intelligence import (
    DuplicatePolicy,
    RightsLevel,
    SearchFilters,
    SearchMode,
    UsageSignalType,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateAssetIndexRequest(ApiModel):
    analyzer_version: str = Field(min_length=1, max_length=160)


class ActivateAssetIndexRequest(ApiModel):
    approved: bool
    reason: str = Field(min_length=1, max_length=2000)
    minimum_coverage_ratio: float = Field(default=0.95, ge=0, le=1)


class SearchScopeRequest(ApiModel):
    project_ids: tuple[UUID, ...] | None = None
    brand_ids: tuple[UUID, ...] | None = None
    permission_tags: tuple[str, ...] = ()
    allowed_rights: tuple[RightsLevel, ...] = (
        "unknown", "owned", "licensed", "public_domain", "restricted"
    )
    commercial_use: bool = False


class AssetSearchBody(ApiModel):
    query: str = Field(default="", max_length=4000)
    mode: SearchMode = "HYBRID"
    scope: SearchScopeRequest = Field(default_factory=SearchScopeRequest)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    query_embedding: tuple[float, ...] | None = None
    similar_to_asset_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)


class DuplicateSearchRequest(ApiModel):
    scope: SearchScopeRequest = Field(default_factory=SearchScopeRequest)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    policy: DuplicatePolicy = Field(
        default_factory=lambda: DuplicatePolicy(
            version="node45-v1",
            perceptual_max_hamming=8,
            semantic_similarity_floor=0.92,
        )
    )


class UsageFeedbackRequest(ApiModel):
    signal: UsageSignalType
    project_id: UUID | None = None
    occurred_at: datetime | None = None
