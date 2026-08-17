from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ExportFormat(StrEnum):
    ORIGINAL = "ORIGINAL"
    PNG = "PNG"
    JPEG = "JPEG"
    MP4 = "MP4"
    PDF = "PDF"
    PPTX = "PPTX"


class ExportJobStatus(StrEnum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RENDERING = "RENDERING"
    PACKAGING = "PACKAGING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ExportSourceFile:
    file_id: str
    role: str
    bucket: str
    storage_key: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        _sha256(self.checksum_sha256, "source checksum")
        if not self.bucket or not self.storage_key or self.size_bytes < 0:
            raise ValueError("invalid source storage metadata")
        _internal_storage_key(self.storage_key)


@dataclass(frozen=True, slots=True)
class ArtifactVersionSnapshot:
    organization_id: str
    project_id: str
    artifact_id: str
    artifact_version_id: str
    artifact_type: str
    version_number: int
    status: str
    content_hash: str
    primary_file_id: str | None
    files: tuple[ExportSourceFile, ...]
    rights_review_status: str
    captured_at: datetime

    def __post_init__(self) -> None:
        _sha256(self.content_hash, "artifact content hash")
        if self.version_number < 1 or not self.files:
            raise ValueError("invalid ArtifactVersion snapshot")
        if self.status != "APPROVED":
            raise ValueError("EXPORT_ARTIFACT_VERSION_NOT_APPROVED")
        if self.rights_review_status == "REJECTED":
            raise ValueError("EXPORT_RIGHTS_REJECTED")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("snapshot timestamp must be timezone-aware")

    def primary_file(self) -> ExportSourceFile:
        if self.primary_file_id:
            for item in self.files:
                if item.file_id == self.primary_file_id:
                    return item
            raise ValueError("EXPORT_PRIMARY_FILE_NOT_FOUND")
        originals = [item for item in self.files if item.role == "original"]
        if len(originals) == 1:
            return originals[0]
        if len(self.files) == 1:
            return self.files[0]
        raise ValueError("EXPORT_PRIMARY_FILE_AMBIGUOUS")


@dataclass(frozen=True, slots=True)
class ExportRequestItem:
    artifact_version_id: str
    target_format: ExportFormat
    output_name: str

    def __post_init__(self) -> None:
        if not self.artifact_version_id:
            raise ValueError("exact ArtifactVersion id is required")
        _safe_name(self.output_name)


@dataclass(frozen=True, slots=True)
class ExportTaskSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    requested_by: str
    items: tuple[ExportRequestItem, ...]
    download_ttl_seconds: int = 900
    force_zip: bool = False
    package_name: str = "export"
    max_total_bytes: int = 2_000_000_000

    def __post_init__(self) -> None:
        if not all((self.organization_id, self.project_id, self.task_id, self.operation_id, self.requested_by)):
            raise ValueError("export tenant/task/operation/actor identifiers are required")
        if not self.items or len(self.items) > 500:
            raise ValueError("export item count must be between 1 and 500")
        if len({item.artifact_version_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate ArtifactVersion ids are not allowed")
        if len({item.output_name for item in self.items}) != len(self.items):
            raise ValueError("duplicate export output names are not allowed")
        if self.download_ttl_seconds < 60 or self.download_ttl_seconds > 3600:
            raise ValueError("download TTL must be between 60 and 3600 seconds")
        if self.max_total_bytes <= 0 or self.max_total_bytes > 10_000_000_000:
            raise ValueError("invalid export byte limit")
        _safe_name(self.package_name)

    def semantic_hash(self) -> str:
        payload = json.dumps(_jsonable(asdict(self)), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ExportItemRuntime:
    request: ExportRequestItem
    snapshot: ArtifactVersionSnapshot


@dataclass(frozen=True, slots=True)
class ExportedFile:
    name: str
    mime_type: str
    bucket: str
    storage_key: str
    size_bytes: int
    checksum_sha256: str
    renderer_version: str
    source_artifact_id: str
    source_artifact_version_id: str
    source_file_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _safe_name(self.name)
        _sha256(self.checksum_sha256, "export checksum")
        if self.size_bytes < 0 or not self.bucket or not self.storage_key:
            raise ValueError("invalid exported file storage metadata")
        _internal_storage_key(self.storage_key)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    name: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    artifact_id: str
    artifact_version_id: str
    source_file_ids: tuple[str, ...]
    renderer_version: str


@dataclass(frozen=True, slots=True)
class ExportManifest:
    schema_version: str
    organization_id: str
    project_id: str
    export_job_id: str
    operation_id: str
    created_at: datetime
    exporter_version: str
    entries: tuple[ManifestEntry, ...]


@dataclass(frozen=True, slots=True)
class DownloadPackage:
    package_id: str
    bucket: str
    storage_key: str
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    manifest: ExportManifest
    is_archive: bool

    def __post_init__(self) -> None:
        _safe_name(self.filename)
        _sha256(self.checksum_sha256, "package checksum")
        _internal_storage_key(self.storage_key)


@dataclass(frozen=True, slots=True)
class DownloadGrant:
    grant_id: str
    package_id: str
    actor_id: str
    expires_at: datetime
    url: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("grant expiry must be timezone-aware")
        if not self.url:
            raise ValueError("download grant URL is required")


@dataclass(frozen=True, slots=True)
class ExportJob:
    job_id: str
    spec: ExportTaskSpec
    status: ExportJobStatus
    items: tuple[ExportItemRuntime, ...]
    runtime_job_id: str | None = None
    outputs: tuple[ExportedFile, ...] = ()
    package: DownloadPackage | None = None
    error_code: str | None = None


def _safe_name(value: str) -> str:
    stripped = value.strip()
    if not stripped or stripped in {".", ".."} or len(stripped) > 240:
        raise ValueError("EXPORT_FILENAME_INVALID")
    if any(token in stripped for token in ("/", "\\", "\x00", "\n", "\r")):
        raise ValueError("EXPORT_FILENAME_INVALID")
    return stripped


def _internal_storage_key(value: str) -> None:
    if not value or value.startswith("http") or "://" in value or "?X-Amz-Signature=" in value:
        raise ValueError("export storage key must be internal")


def _sha256(value: str, label: str) -> None:
    if len(value) != 64 or value.lower() != value:
        raise ValueError(f"{label} must be lowercase sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be lowercase sha256") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    return value
