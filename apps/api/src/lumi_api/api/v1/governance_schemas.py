from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GovernanceApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LegalHoldRequest(GovernanceApiModel):
    hold_key: str = Field(min_length=1, max_length=160)
    scope_type: str = Field(min_length=1, max_length=40)
    scope_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=8, max_length=1000)


class ReasonRequest(GovernanceApiModel):
    reason: str = Field(min_length=8, max_length=1000)


class DeletionRequestInput(GovernanceApiModel):
    subject_type: str = Field(pattern=r"^(USER|ORGANIZATION)$")
    subject_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=8, max_length=1000)


class AuditExportInput(GovernanceApiModel):
    export_format: str = Field(pattern=r"^(JSON|CSV)$")
    filters: dict[str, Any] = Field(default_factory=dict)
