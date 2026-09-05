from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateAssetUploadRequest(StrictModel):
    project_id: UUID
    original_name: str = Field(min_length=1, max_length=512)
    declared_mime_type: str = Field(min_length=1, max_length=255)
    declared_size: int = Field(ge=1)
    checksum_sha256: str = Field(pattern="^[0-9a-fA-F]{64}$")
    rights_assertion: Literal["USER_OWNED", "LICENSED", "UNKNOWN"]
    source_reference: str | None = Field(default=None, max_length=2048)
    upload_mode: Literal["single", "multipart"] = "single"


class SignedPutResource(StrictModel):
    url: str
    method: Literal["PUT"] = "PUT"
    required_headers: dict[str, str]
    expires_at: datetime


class CreateAssetUploadResponse(StrictModel):
    asset_id: UUID
    upload_session_id: UUID
    file_id: UUID
    upload_mode: Literal["single", "multipart"]
    status: Literal["pending"] = "pending"
    upload: SignedPutResource | None = None
    expires_at: datetime


class SignUploadPartRequest(StrictModel):
    checksum_sha256: str | None = Field(default=None, pattern="^[0-9a-fA-F]{64}$")


class SignUploadPartResponse(StrictModel):
    part_number: int = Field(ge=1, le=10_000)
    url: str
    method: Literal["PUT"] = "PUT"
    required_headers: dict[str, str]
    expires_at: datetime


class CompletedPartRequest(StrictModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=512)
    checksum_sha256: str | None = Field(default=None, pattern="^[0-9a-fA-F]{64}$")


class CompleteAssetUploadRequest(StrictModel):
    parts: list[CompletedPartRequest] = Field(default_factory=list, max_length=10_000)


class CompleteAssetUploadResponse(StrictModel):
    asset_id: UUID
    upload_session_id: UUID
    status: Literal["scanning"] = "scanning"
    validation_run_id: UUID


class AssetResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    kind: str
    source: str
    original_name: str | None = None
    status: Literal["uploading", "scanning", "ready", "rejected"]
    rejection_code: str | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class SignedAssetDownloadResponse(StrictModel):
    asset_id: UUID
    variant: str
    url: str
    expires_at: datetime
