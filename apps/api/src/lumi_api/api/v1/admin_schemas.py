from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdminApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReasonRequest(AdminApiModel):
    reason: str = Field(min_length=8, max_length=1000)


class ProviderOverrideRequest(ReasonRequest):
    provider: str = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=255)
    capability: str | None = Field(default=None, max_length=128)
    action: str
    expires_at: datetime | None = None


class FeatureFlagRequest(ReasonRequest):
    flag_key: str = Field(min_length=1, max_length=160)
    scope: str
    target_id: str | None = Field(default=None, max_length=255)
    value: dict[str, Any]
    owner: str = Field(min_length=1, max_length=160)
    expires_at: datetime | None = None


class BreakGlassRequest(ReasonRequest):
    scope: str = Field(min_length=1, max_length=120)
    target_type: str = Field(min_length=1, max_length=80)
    target_id: str = Field(min_length=1, max_length=255)
    ttl_minutes: int = Field(default=15, ge=1, le=30)


class RegistryPromotionRequest(ReasonRequest):
    registry_kind: str = Field(min_length=1, max_length=40)
    key: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=160)
