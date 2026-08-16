# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

_SHA256 = r"^[0-9a-f]{64}$"
_GIT_SHA = r"^[0-9a-f]{40}$"


class ArtifactContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ArtifactType(StrEnum):
    DESIGN_DOCUMENT = "DESIGN_DOCUMENT"
    RASTER_IMAGE = "RASTER_IMAGE"
    VECTOR_IMAGE = "VECTOR_IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    PDF = "PDF"
    HTML = "HTML"
    ARCHIVE = "ARCHIVE"
    EXPORT_PACKAGE = "EXPORT_PACKAGE"


class ArtifactVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class LineageEdgeType(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    EDITED_FROM = "EDITED_FROM"
    GENERATED_FROM = "GENERATED_FROM"
    COMPOSED_FROM = "COMPOSED_FROM"
    RESIZED_FROM = "RESIZED_FROM"
    EXPORTED_FROM = "EXPORTED_FROM"
    REFERENCE_USED = "REFERENCE_USED"


class FileRole(StrEnum):
    PREVIEW = "preview"
    ORIGINAL = "original"
    THUMBNAIL = "thumbnail"
    WEB_OPTIMIZED = "web-optimized"
    PRINT_PDF = "print-pdf"
    LAYER_DATA = "layer-data"


class RightsReviewStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CreatedByType(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    IMPORT = "IMPORT"


class RightsPolicy(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.rights/1.0", pattern=r"^lumi\.rights/1\.0$"
    )
    source_type: str = Field(min_length=1, max_length=80)
    owner_assertion: str = Field(min_length=1, max_length=240)
    license_type: str = Field(min_length=1, max_length=120)
    commercial_use: bool | None = None
    redistribution: bool | None = None
    training_use: bool | None = None
    attribution_required: bool = False
    source_reference: str | None = Field(default=None, max_length=2_000)
    review_status: RightsReviewStatus = RightsReviewStatus.UNREVIEWED


class ArtifactFile(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.artifact-file/1.0", pattern=r"^lumi\.artifact-file/1\.0$"
    )
    id: UUID
    role: FileRole
    bucket: str = Field(min_length=1, max_length=128)
    storage_key: str = Field(min_length=1, max_length=2_000)
    mime_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=_SHA256)
    width: int | None = Field(default=None, ge=1, le=1_000_000)
    height: int | None = Field(default=None, ge=1, le=1_000_000)
    duration_ms: int | None = Field(default=None, ge=0)
    metadata: tuple[tuple[str, str], ...] = Field(default=(), max_length=128)

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("artifact file id must be UUIDv7")
        return value

    @field_validator("metadata")
    @classmethod
    def canonicalize_metadata(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        keys = [key for key, _ in value]
        if len(keys) != len(set(keys)):
            raise ValueError("artifact file metadata keys must be unique")
        if any(not key.strip() or len(key) > 120 for key in keys):
            raise ValueError("artifact file metadata keys must be non-empty and <=120 chars")
        if any(len(item) > 2_000 for _, item in value):
            raise ValueError("artifact file metadata values must be <=2000 chars")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def dimensions_are_paired(self) -> ArtifactFile:
        if (self.width is None) != (self.height is None):
            raise ValueError("artifact file width/height must be supplied together")
        if "?X-Amz-Signature=" in self.storage_key or self.storage_key.startswith("http"):
            raise ValueError("artifact files must store object keys, not signed/public URLs")
        return self


class SkillVersionRef(ArtifactContractModel):
    skill_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=120)


class ProvenanceRecord(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.provenance/1.0", pattern=r"^lumi\.provenance/1\.0$"
    )
    agent_run_id: UUID | None = None
    task_id: UUID | None = None
    generation_id: UUID | None = None
    provider: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=200)
    provider_request_id: str | None = Field(default=None, max_length=300)
    prompt_hash: str | None = Field(default=None, pattern=_SHA256)
    prompt_ref: str | None = Field(default=None, max_length=500)
    prompt_template_version: str | None = Field(default=None, max_length=120)
    input_asset_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    input_artifact_version_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    design_ir_schema_version: str | None = Field(default=None, max_length=80)
    constraint_snapshot_hash: str | None = Field(default=None, pattern=_SHA256)
    recipe_version: str | None = Field(default=None, max_length=120)
    skill_versions: tuple[SkillVersionRef, ...] = Field(default=(), max_length=256)
    code_git_sha: str = Field(pattern=_GIT_SHA)

    @field_validator("input_asset_ids", "input_artifact_version_ids")
    @classmethod
    def canonicalize_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("provenance input ids must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("skill_versions")
    @classmethod
    def canonicalize_skills(
        cls, value: tuple[SkillVersionRef, ...]
    ) -> tuple[SkillVersionRef, ...]:
        ids = [item.skill_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("skill ids must be unique within provenance")
        return tuple(sorted(value, key=lambda item: item.skill_id))

    @model_validator(mode="after")
    def generated_records_are_traceable(self) -> ProvenanceRecord:
        if self.generation_id is not None and (
            not self.provider or not self.model or not self.prompt_hash
        ):
            raise ValueError(
                "generation provenance requires provider, model and prompt_hash"
            )
        return self


class Artifact(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.artifact/1.0", pattern=r"^lumi\.artifact/1\.0$"
    )
    id: UUID
    organization_id: UUID
    project_id: UUID
    type: ArtifactType
    name: str = Field(min_length=1, max_length=240)
    design_document_id: UUID | None = None
    rights: RightsPolicy
    archived_at: datetime | None = None
    retention_until: datetime | None = None
    legal_hold: bool = False

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("artifact id must be UUIDv7")
        return value

    @field_validator("archived_at", "retention_until")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("artifact lifecycle timestamps must be timezone-aware")
        return value


class ArtifactBranch(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.artifact-branch/1.0",
        pattern=r"^lumi\.artifact-branch/1\.0$",
    )
    id: UUID
    organization_id: UUID
    artifact_id: UUID
    name: str = Field(min_length=1, max_length=120)
    base_version_id: UUID | None = None
    head_version_id: UUID | None = None
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    created_at: datetime

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("artifact branch id must be UUIDv7")
        return value

    @field_validator("created_at")
    @classmethod
    def require_created_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def creator_identity_is_consistent(self) -> ArtifactBranch:
        if (
            self.created_by_type in {CreatedByType.USER, CreatedByType.AGENT}
            and not self.created_by_id
        ):
            raise ValueError("user/agent branch creator requires created_by_id")
        return self


class ArtifactVersion(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.artifact-version/1.0",
        pattern=r"^lumi\.artifact-version/1\.0$",
    )
    id: UUID
    organization_id: UUID
    artifact_id: UUID
    branch_id: UUID
    parent_version_id: UUID | None = None
    version_number: int = Field(ge=1)
    status: ArtifactVersionStatus = ArtifactVersionStatus.DRAFT
    content_hash: str = Field(pattern=_SHA256)
    primary_file_id: UUID | None = None
    design_document_version_id: UUID | None = None
    quality_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    constraint_snapshot_hash: str | None = Field(default=None, pattern=_SHA256)
    created_by_type: CreatedByType
    created_by_id: str | None = Field(default=None, max_length=200)
    created_at: datetime
    files: tuple[ArtifactFile, ...] = Field(default=(), max_length=128)
    provenance: ProvenanceRecord
    rights: RightsPolicy

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("artifact version id must be UUIDv7")
        return value

    @field_validator("created_at")
    @classmethod
    def require_version_created_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_version_identity(self) -> ArtifactVersion:
        if self.parent_version_id == self.id:
            raise ValueError("artifact version cannot parent itself")
        file_ids = [item.id for item in self.files]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("artifact version file ids must be unique")
        storage_locations = [(item.bucket, item.storage_key) for item in self.files]
        if len(storage_locations) != len(set(storage_locations)):
            raise ValueError("artifact version file storage locations must be unique")
        if self.primary_file_id is not None and self.primary_file_id not in set(file_ids):
            raise ValueError("primary_file_id must reference a version file")
        if (
            self.created_by_type in {CreatedByType.USER, CreatedByType.AGENT}
            and not self.created_by_id
        ):
            raise ValueError("user/agent version creator requires created_by_id")
        if (
            self.constraint_snapshot_hash is not None
            and self.provenance.constraint_snapshot_hash is not None
            and self.constraint_snapshot_hash != self.provenance.constraint_snapshot_hash
        ):
            raise ValueError("version and provenance constraint snapshot hashes must match")
        return self


class LineageEdge(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.lineage-edge/1.0", pattern=r"^lumi\.lineage-edge/1\.0$"
    )
    id: UUID
    organization_id: UUID
    artifact_version_id: UUID
    source_artifact_version_id: UUID
    type: LineageEdgeType
    created_at: datetime
    metadata: tuple[tuple[str, str], ...] = Field(default=(), max_length=128)

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("lineage edge id must be UUIDv7")
        return value

    @field_validator("created_at")
    @classmethod
    def require_edge_created_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def reject_self_edge(self) -> LineageEdge:
        if self.artifact_version_id == self.source_artifact_version_id:
            raise ValueError("lineage edge cannot reference the same version")
        return self


class ArtifactSnapshot(ArtifactContractModel):
    artifact: Artifact
    branches: tuple[ArtifactBranch, ...]
    versions: tuple[ArtifactVersion, ...]
    lineage: tuple[LineageEdge, ...]


class ProvenanceManifest(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.export-provenance/1.0",
        pattern=r"^lumi\.export-provenance/1\.0$",
    )
    artifact_version_id: UUID
    created_at: datetime
    source_artifact_version_ids: tuple[UUID, ...]
    source_asset_ids: tuple[UUID, ...]
    models: tuple[tuple[str, str], ...]
    rights: tuple[RightsPolicy, ...]
    checksums: tuple[str, ...]
    code_git_sha: str = Field(pattern=_GIT_SHA)
    constraint_snapshot_hash: str | None = Field(default=None, pattern=_SHA256)

    @field_validator("created_at")
    @classmethod
    def require_manifest_created_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value
