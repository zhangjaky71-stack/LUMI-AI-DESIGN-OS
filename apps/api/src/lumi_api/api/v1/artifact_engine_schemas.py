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


class RestoreVersionRequest(ApiModel):
    target_branch_id: UUID
    expected_head_version_id: UUID | None = None
    provenance: ProvenanceEnvelope
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)


class ApproveVersionRequest(ApiModel):
    approved_by_id: str = Field(min_length=1, max_length=200)
    validation_ref: str = Field(min_length=1, max_length=500)


class MarkReadyRequest(ApiModel):
    occurred_at: datetime | None = None
