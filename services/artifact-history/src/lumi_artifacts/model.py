from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, Mapping

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")

ArtifactType = Literal["DESIGN_DOCUMENT","RASTER_IMAGE","VECTOR_IMAGE","VIDEO","AUDIO","PDF","HTML","ARCHIVE","EXPORT_PACKAGE"]
VersionStatus = Literal["DRAFT", "READY", "APPROVED", "REJECTED", "ARCHIVED"]
LineageType = Literal["DERIVED_FROM","EDITED_FROM","GENERATED_FROM","COMPOSED_FROM","RESIZED_FROM","EXPORTED_FROM","REFERENCE_USED"]
TriState = Literal["ALLOWED", "DENIED", "UNKNOWN"]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    organization_id: str
    project_id: str
    type: ArtifactType
    title: str
    archived: bool = False


@dataclass(frozen=True, slots=True)
class ArtifactBranch:
    id: str
    organization_id: str
    artifact_id: str
    name: str
    base_version_id: str | None
    head_version_id: str | None
    created_by: str


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    id: str
    organization_id: str
    artifact_id: str
    branch_id: str
    parent_version_id: str | None
    schema_version: str
    version_number: int
    status: VersionStatus
    content_hash: str
    constraint_snapshot_hash: str
    created_by_type: Literal["USER", "AGENT", "SYSTEM"]
    created_by_id: str
    created_at: datetime
    primary_file_id: str | None = None
    design_document_version_id: str | None = None
    quality_score: float | None = None

    def __post_init__(self) -> None:
        if self.version_number < 1:
            raise ValueError("version_number must be >= 1")
        _require_sha256(self.content_hash, "content_hash")
        _require_sha256(self.constraint_snapshot_hash, "constraint_snapshot_hash")
        if self.quality_score is not None and not 0 <= self.quality_score <= 1:
            raise ValueError("quality_score must be in [0,1]")

    @property
    def immutable_content_identity(self) -> tuple[Any, ...]:
        return (
            self.organization_id,
            self.artifact_id,
            self.branch_id,
            self.parent_version_id,
            self.schema_version,
            self.version_number,
            self.content_hash,
            self.constraint_snapshot_hash,
            self.primary_file_id,
            self.design_document_version_id,
            self.created_by_type,
            self.created_by_id,
            self.created_at,
        )


@dataclass(frozen=True, slots=True)
class ArtifactFile:
    id: str
    organization_id: str
    artifact_version_id: str
    role: Literal["PREVIEW", "ORIGINAL", "THUMBNAIL", "WEB_OPTIMIZED", "PRINT_PDF", "LAYER_DATA"]
    storage_key: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.storage_key or "://" in self.storage_key:
            raise ValueError("storage_key must be a durable object key, not a URL")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        _require_sha256(self.checksum_sha256, "checksum_sha256")
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class LineageEdge:
    id: str
    organization_id: str
    from_version_id: str
    to_version_id: str
    type: LineageType
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.from_version_id == self.to_version_id:
            raise ValueError("lineage self-loop is forbidden")
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    artifact_version_id: str
    organization_id: str
    constraint_snapshot_hash: str
    code_git_sha: str
    agent_run_id: str | None = None
    task_id: str | None = None
    generation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    prompt_hash: str | None = None
    prompt_template_version: str | None = None
    input_asset_ids: tuple[str, ...] = ()
    input_artifact_version_ids: tuple[str, ...] = ()
    design_ir_schema_version: str | None = None
    recipe_version: str | None = None
    skill_versions: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_sha256(self.constraint_snapshot_hash, "constraint_snapshot_hash")
        if self.prompt_hash is not None:
            _require_sha256(self.prompt_hash, "prompt_hash")
        if not _GIT_SHA.fullmatch(self.code_git_sha):
            raise ValueError("code_git_sha must be lowercase 40-character git SHA")
        object.__setattr__(self, "input_asset_ids", tuple(dict.fromkeys(self.input_asset_ids)))
        object.__setattr__(self, "input_artifact_version_ids", tuple(dict.fromkeys(self.input_artifact_version_ids)))
        object.__setattr__(self, "skill_versions", _freeze(self.skill_versions))


@dataclass(frozen=True, slots=True)
class RightsRecord:
    subject_type: Literal["ASSET", "ARTIFACT_VERSION"]
    subject_id: str
    organization_id: str
    source_type: Literal["USER_UPLOAD","GENERATED","LICENSED","PUBLIC_DOMAIN","THIRD_PARTY","UNKNOWN"]
    owner_assertion: str | None
    license_type: Literal["OWNED","COMMERCIAL_LICENSE","NONCOMMERCIAL","PUBLIC_DOMAIN","CC_BY","CC_BY_SA","UNKNOWN"]
    commercial_use: TriState
    redistribution: TriState
    training_use: TriState
    attribution_required: bool
    source_reference: str | None
    review_status: Literal["UNREVIEWED", "ASSERTED", "VERIFIED", "RESTRICTED"]
