from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lumi_api.domain.ids import new_uuid7
from lumi_api.domain.states import ProjectStatus


class ProjectModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QualityProfile(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


class DataRetentionProfile(StrEnum):
    STANDARD = "standard"
    EXTENDED = "extended"
    RESTRICTED = "restricted"


class ProjectBrief(ProjectModel):
    schema_version: str = Field(
        default="lumi.project-brief/1.0",
        pattern=r"^lumi\.project-brief/1\.0$",
    )
    objective: str = Field(default="", max_length=20_000)
    audience: tuple[str, ...] = Field(default=(), max_length=100)
    brand_context: str = Field(default="", max_length=20_000)
    deliverables: tuple[str, ...] = Field(default=(), max_length=200)
    channels: tuple[str, ...] = Field(default=(), max_length=100)
    visual_direction: str = Field(default="", max_length=20_000)
    copy_requirements: tuple[str, ...] = Field(default=(), max_length=200)
    constraints: tuple[str, ...] = Field(default=(), max_length=500)
    references: tuple[str, ...] = Field(default=(), max_length=200)
    locale: str = Field(default="en-US", min_length=2, max_length=35)
    notes: str = Field(default="", max_length=50_000)
    source_input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_input_ref: str | None = Field(default=None, max_length=2_000)

    @field_validator(
        "audience",
        "deliverables",
        "channels",
        "copy_requirements",
        "constraints",
        "references",
    )
    @classmethod
    def normalize_sequences(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value if item.strip())
        if len(normalized) != len(set(normalized)):
            raise ValueError("brief list values must be unique")
        return normalized


class ProjectSettings(ProjectModel):
    schema_version: str = Field(
        default="lumi.project-settings/1.0",
        pattern=r"^lumi\.project-settings/1\.0$",
    )
    default_locale: str = Field(default="en-US", min_length=2, max_length=35)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    cost_budget_default: Decimal | None = Field(default=None, ge=0)
    cost_budget_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    quality_profile: QualityProfile = QualityProfile.BALANCED
    model_policy_id: UUID | None = None
    data_retention_profile: DataRetentionProfile = DataRetentionProfile.STANDARD

    @model_validator(mode="after")
    def reject_secret_like_fields(self) -> "ProjectSettings":
        payload = self.model_dump(mode="json")
        forbidden = ("secret", "token", "password", "api_key", "apikey", "credential")
        if any(marker in key.casefold() for key in payload for marker in forbidden):
            raise ValueError("provider secrets are forbidden in project settings")
        return self


class ProjectRecord(ProjectModel):
    id: UUID
    organization_id: UUID
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=240)
    status: ProjectStatus = ProjectStatus.DRAFT
    brief: ProjectBrief = Field(default_factory=ProjectBrief)
    brief_version: int = Field(default=1, ge=1)
    brand_id: UUID | None = None
    active_branch_id: UUID | None = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    created_by: UUID | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class BriefVersion(ProjectModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    version: int = Field(ge=1)
    brief: ProjectBrief
    changed_by: UUID | None = None
    change_reason: str | None = Field(default=None, max_length=1_000)
    created_at: datetime


class DefaultProjectBranch(ProjectModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    name: str = Field(default="main", pattern=r"^main$")
    created_at: datetime


class ProjectSummary(ProjectModel):
    organization_id: UUID
    project_id: UUID
    latest_artifact_preview_id: UUID | None = None
    last_activity_at: datetime
    active_run_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)
    projection_version: int = Field(default=1, ge=1)


class ProjectEventType(StrEnum):
    CREATED = "project.created"
    UPDATED = "project.updated"
    PAUSED = "project.paused"
    ARCHIVED = "project.archived"
    RESTORED = "project.restored"
    BRIEF_UPDATED = "project.brief.updated"


class ProjectEvent(ProjectModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    event_type: ProjectEventType
    actor_id: str | None = None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ProjectAuditEntry(ProjectModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    actor_id: str | None = Field(default=None, max_length=200)
    action: ProjectEventType
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class ProjectListQuery(ProjectModel):
    organization_id: UUID
    status: ProjectStatus | None = None
    workspace_id: UUID | None = None
    created_by: UUID | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    name_query: str | None = Field(default=None, min_length=1, max_length=240)
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_range(self) -> "ProjectListQuery":
        if self.updated_from and self.updated_to and self.updated_from > self.updated_to:
            raise ValueError("updated_from must not be after updated_to")
        return self


class ProjectPage(ProjectModel):
    items: tuple[ProjectRecord, ...]
    next_cursor: str | None = None


class ProjectCommandError(ValueError):
    pass
