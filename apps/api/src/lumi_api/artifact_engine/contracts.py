from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator

from lumi_api.artifacts.models import (
    ArtifactFile,
    ArtifactType,
    CreatedByType,
    LineageEdgeType,
    ProvenanceRecord,
    RightsPolicy,
)


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TraceabilityStatus(StrEnum):
    FULLY_TRACEABLE = "FULLY_TRACEABLE"
    PARTIAL = "PARTIAL"


class ProvenanceEnvelope(RuntimeModel):
    record: ProvenanceRecord
    compiler_version: str | None = Field(default=None, max_length=120)
    agent_version: str | None = Field(default=None, max_length=120)


class ProvenanceCompleteness(RuntimeModel):
    score: FiniteFloat = Field(ge=0, le=1)
    status: TraceabilityStatus
    missing_fields: tuple[str, ...] = ()


class InitialVersionCreateCommand(RuntimeModel):
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[ArtifactFile, ...] = Field(default=(), max_length=128)
    provenance: ProvenanceEnvelope
    rights: RightsPolicy
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    primary_file_id: UUID | None = None
    design_document_version_id: UUID | None = None
    quality_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    constraint_snapshot_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    lineage_sources: tuple[tuple[UUID, LineageEdgeType], ...] = ()


class ArtifactCreateCommand(RuntimeModel):
    organization_id: UUID
    project_id: UUID
    artifact_type: ArtifactType
    name: str = Field(min_length=1, max_length=240)
    rights: RightsPolicy
    design_document_id: UUID | None = None
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    created_at: datetime
    initial_version: InitialVersionCreateCommand | None = None

    @field_validator("created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class VersionCreateCommand(RuntimeModel):
    branch_id: UUID
    expected_head_version_id: UUID | None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[ArtifactFile, ...] = Field(default=(), max_length=128)
    provenance: ProvenanceEnvelope
    rights: RightsPolicy
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    created_at: datetime
    primary_file_id: UUID | None = None
    design_document_version_id: UUID | None = None
    quality_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    constraint_snapshot_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    lineage_sources: tuple[tuple[UUID, LineageEdgeType], ...] = ()

    @field_validator("created_at")
    @classmethod
    def aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class ApprovalRecord(RuntimeModel):
    id: UUID
    organization_id: UUID
    artifact_version_id: UUID
    approved_by_id: str = Field(min_length=1, max_length=200)
    approved_at: datetime
    validation_ref: str = Field(min_length=1, max_length=500)


class StorageObjectMetadata(RuntimeModel):
    organization_id: UUID
    bucket: str = Field(min_length=1, max_length=128)
    storage_key: str = Field(min_length=1, max_length=2_000)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=255)

    @property
    def location(self) -> tuple[str, str]:
        return (self.bucket, self.storage_key)


class ArtifactOutboxEvent(RuntimeModel):
    id: UUID
    organization_id: UUID
    event_type: str = Field(min_length=1, max_length=120)
    aggregate_id: UUID
    aggregate_version_id: UUID | None = None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactCompareKind(StrEnum):
    DESIGN_SEMANTIC = "DESIGN_SEMANTIC"
    RASTER_METADATA = "RASTER_METADATA"
    GENERIC_METADATA = "GENERIC_METADATA"


class ArtifactCompareResult(RuntimeModel):
    left_version_id: UUID
    right_version_id: UUID
    kind: ArtifactCompareKind
    equal_content_hash: bool
    semantic_diff: dict[str, Any] | None = None
    visual_metrics: dict[str, FiniteFloat] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GcMarkState(StrEnum):
    MARKED = "MARKED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"


class GcMark(RuntimeModel):
    id: UUID
    organization_id: UUID
    bucket: str
    storage_key: str
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    marked_at: datetime
    not_before: datetime
    state: GcMarkState = GcMarkState.MARKED
    completed_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)

    @property
    def location(self) -> tuple[str, str]:
        return (self.bucket, self.storage_key)


class GcAudit(RuntimeModel):
    id: UUID
    organization_id: UUID
    gc_mark_id: UUID
    action: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    bucket: str
    storage_key: str
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    detail: str | None = Field(default=None, max_length=500)
