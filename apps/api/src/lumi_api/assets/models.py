from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lumi_api.domain.ids import new_uuid7


class AssetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssetStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    VERIFYING = "verifying"
    SCANNING = "scanning"
    READY = "ready"
    REJECTED = "rejected"
    DELETED = "deleted"


class UploadStatus(StrEnum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ABORTED = "aborted"


class ScanStatus(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class RightsAssertion(StrEnum):
    USER_OWNED = "USER_OWNED"
    LICENSED = "LICENSED"
    UNKNOWN = "UNKNOWN"


class MediaKind(StrEnum):
    IMAGE = "image"
    VECTOR = "vector"
    DOCUMENT = "document"
    VIDEO = "video"
    FONT = "font"


class AssetFileRole(StrEnum):
    ORIGINAL = "original"
    SANITIZED = "sanitized"
    THUMBNAIL = "thumbnail"
    MEDIUM = "medium"
    POSTER = "poster"


class UploadMode(StrEnum):
    SINGLE_PUT = "single_put"
    MULTIPART = "multipart"


class SignedRequest(AssetModel):
    method: Literal["GET", "PUT", "POST", "DELETE", "HEAD"]
    url: str = Field(min_length=1, max_length=8_000)
    expires_at: datetime
    headers: dict[str, str] = Field(default_factory=dict)
    upload_id: str | None = Field(default=None, max_length=1_000)


class ObjectHead(AssetModel):
    bucket: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=2_048)
    exists: bool = True
    byte_size: int = Field(ge=0)
    content_type: str | None = Field(default=None, max_length=255)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    etag: str | None = Field(default=None, max_length=255)
    metadata: dict[str, str] = Field(default_factory=dict)


class QuotaPolicy(AssetModel):
    max_file_bytes: int = Field(default=250 * 1024 * 1024, ge=1)
    max_org_storage_bytes: int = Field(default=20 * 1024 * 1024 * 1024, ge=1)
    multipart_threshold_bytes: int = Field(default=32 * 1024 * 1024, ge=5 * 1024 * 1024)
    upload_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    download_ttl_seconds: int = Field(default=300, ge=30, le=900)
    require_scanner: bool = True


class AssetRecord(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    source: str = Field(default="upload", min_length=1, max_length=64)
    original_filename: str = Field(min_length=1, max_length=255)
    declared_mime_type: str = Field(min_length=1, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    media_kind: MediaKind | None = None
    status: AssetStatus = AssetStatus.PENDING
    rights_assertion: RightsAssertion = RightsAssertion.UNKNOWN
    rights_source_uri: str | None = Field(default=None, max_length=2_000)
    rejected_reason: str | None = Field(default=None, max_length=1_000)
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AssetFileRecord(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    asset_id: UUID
    role: AssetFileRole
    bucket: str = Field(min_length=1, max_length=128)
    object_key: str = Field(min_length=1, max_length=2_048)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=255)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, ge=0)
    codec: str | None = Field(default=None, max_length=120)
    color_profile: str | None = Field(default=None, max_length=120)
    has_alpha: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    verified_at: datetime


class UploadSession(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    asset_id: UUID
    file_id: UUID
    bucket: str = Field(min_length=1, max_length=128)
    object_key: str = Field(min_length=1, max_length=2_048)
    original_filename: str = Field(min_length=1, max_length=255)
    declared_mime_type: str = Field(min_length=1, max_length=255)
    expected_size: int = Field(ge=1)
    expected_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: UploadMode
    status: UploadStatus = UploadStatus.PENDING
    storage_upload_id: str | None = Field(default=None, max_length=1_000)
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> UploadSession:
        for value in (self.created_at, self.expires_at, self.completed_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("upload timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("upload expires_at must be after created_at")
        return self


class FileScanResult(AssetModel):
    status: ScanStatus
    engine: str = Field(min_length=1, max_length=120)
    signature: str | None = Field(default=None, max_length=500)
    detail: str | None = Field(default=None, max_length=1_000)


class ValidationReport(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    asset_id: UUID
    upload_session_id: UUID
    expected_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actual_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_size: int = Field(ge=0)
    actual_size: int = Field(ge=0)
    sniffed_mime_type: str = Field(min_length=1, max_length=255)
    media_kind: MediaKind
    scan: FileScanResult
    accepted: bool
    reason_codes: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AssetPreview(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    asset_id: UUID
    source_file_id: UUID
    role: AssetFileRole
    file: AssetFileRecord
    created_at: datetime

    @model_validator(mode="after")
    def validate_preview(self) -> AssetPreview:
        if self.role not in {
            AssetFileRole.THUMBNAIL,
            AssetFileRole.MEDIUM,
            AssetFileRole.POSTER,
        }:
            raise ValueError("preview role must be thumbnail, medium or poster")
        if self.file.role != self.role:
            raise ValueError("preview role and file role must match")
        return self


class AssetEventType(StrEnum):
    UPLOAD_CREATED = "asset.upload.created"
    UPLOAD_COMPLETED = "asset.upload.completed"
    SCAN_FAILED = "asset.scan.failed"
    READY = "asset.ready"
    REJECTED = "asset.rejected"
    PREVIEW_CREATED = "asset.preview.created"


class AssetEvent(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    project_id: UUID
    asset_id: UUID
    event_type: AssetEventType
    occurred_at: datetime
    actor_id: str | None = Field(default=None, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class AssetAuditEntry(AssetModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    asset_id: UUID
    action: str = Field(min_length=1, max_length=120)
    actor_id: str | None = Field(default=None, max_length=200)
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class PreviewResult(AssetModel):
    role: AssetFileRole
    mime_type: str
    content: bytes
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)

    @field_validator("role")
    @classmethod
    def role_is_preview(cls, value: AssetFileRole) -> AssetFileRole:
        if value not in {AssetFileRole.THUMBNAIL, AssetFileRole.MEDIUM, AssetFileRole.POSTER}:
            raise ValueError("preview renderer returned non-preview role")
        return value
