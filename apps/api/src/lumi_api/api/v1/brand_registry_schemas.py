from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BrandCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    profile: dict[str, Any] = Field(default_factory=dict)


class BrandPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    profile: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "BrandPatchRequest":
        if self.name is None and self.profile is None:
            raise ValueError("BRAND_PATCH_REQUIRES_CHANGE")
        return self


class BrandResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    profile: dict[str, Any] = Field(default_factory=dict)
    active_rule_set_version_id: UUID | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class BrandPage(BaseModel):
    items: list[BrandResponse]
    total: int = Field(ge=0)
