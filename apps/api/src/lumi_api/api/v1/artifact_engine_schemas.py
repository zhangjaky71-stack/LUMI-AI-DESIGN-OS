from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_api.artifact_engine import ProvenanceEnvelope
from lumi_api.artifacts.models import (
    Artifact,
    ArtifactBranch,
    ArtifactFile,
    ArtifactType,
    ArtifactVersionStatus,
    CreatedByType,
    LineageEdgeType,
    RightsPolicy,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactBundleResponse(ApiModel):
    artifact: Artifact
    main_branch: ArtifactBranch


class InitialVersionRequest(ApiModel):
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[ArtifactFile, ...] = ()
    provenance: ProvenanceEnvelope
    rights: RightsPolicy
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    primary_file_id: UUID | None = None
    design_document_version_id: UUID | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    constraint_snapshot_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    lineage_sources: tuple[tuple[UUID, LineageEdgeType], ...] = ()


class CreateArtifactRequest(ApiModel):
    artifact_type: ArtifactType
    name: str = Field(min_length=1, max_length=240)
    rights: RightsPolicy
    design_document_id: UUID | None = None
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    initial_version: InitialVersionRequest | None = None


class CreateVersionRequest(ApiModel):
    expected_head_version_id: UUID | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[ArtifactFile, ...] = ()
    provenance: ProvenanceEnvelope
    rights: RightsPolicy
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    primary_file_id: UUID | None = None
    design_document_version_id: UUID | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    constraint_snapshot_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    lineage_sources: tuple[tuple[UUID, LineageEdgeType], ...] = ()


class ForkVersionRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)


class UserForkVersionRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class RestoreVersionRequest(ApiModel):
    target_branch_id: UUID
    expected_head_version_id: UUID | None = None
    provenance: ProvenanceEnvelope
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)


class UserRestoreVersionRequest(ApiModel):
    target_branch_id: UUID
    expected_head_version_id: UUID | None = None


class ApproveVersionRequest(ApiModel):
    approved_by_id: str = Field(min_length=1, max_length=200)
    validation_ref: str = Field(min_length=1, max_length=500)


class MarkReadyRequest(ApiModel):
    occurred_at: datetime | None = None


class VersionPreviewSummary(ApiModel):
    mime_type: str | None = Field(default=None, max_length=255)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)


class ArtifactVersionHistoryItem(ApiModel):
    id: UUID
    artifact_id: UUID
    branch_id: UUID
    parent_version_id: UUID | None = None
    version_number: int = Field(ge=1)
    status: ArtifactVersionStatus
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    design_document_version_id: UUID | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    constraint_snapshot_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    created_at: datetime
    preview: VersionPreviewSummary = VersionPreviewSummary()


class ArtifactVersionHistoryResponse(ApiModel):
    artifact: Artifact
    branches: tuple[ArtifactBranch, ...]
    versions: tuple[ArtifactVersionHistoryItem, ...]


class SafeSkillVersion(ApiModel):
    skill_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=120)


class SafeVersionProvenanceResponse(ApiModel):
    artifact_version_id: UUID
    traceability_score: float = Field(ge=0, le=1)
    traceability_status: str = Field(min_length=1, max_length=64)
    missing_fields: tuple[str, ...] = ()
    agent_run_id: UUID | None = None
    task_id: UUID | None = None
    generation_id: UUID | None = None
    provider: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=200)
    prompt_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    prompt_template_version: str | None = Field(default=None, max_length=120)
    input_asset_ids: tuple[UUID, ...] = ()
    input_artifact_version_ids: tuple[UUID, ...] = ()
    design_ir_schema_version: str | None = Field(default=None, max_length=80)
    constraint_snapshot_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    recipe_version: str | None = Field(default=None, max_length=120)
    skill_versions: tuple[SafeSkillVersion, ...] = ()
    code_git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    compiler_version: str | None = Field(default=None, max_length=120)
    agent_version: str | None = Field(default=None, max_length=120)
