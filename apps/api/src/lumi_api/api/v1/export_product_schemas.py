from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from lumi_export_engine import ExportFormat, ExportJobStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportFormatCapability(ApiModel):
    format: ExportFormat
    label: str = Field(min_length=1, max_length=80)
    output_extension: str = Field(min_length=1, max_length=16)
    copy_through: bool = True


class ExportCapabilitiesResponse(ApiModel):
    artifact_version_id: UUID
    approved: bool
    source_mime_type: str = Field(min_length=1, max_length=255)
    formats: tuple[ExportFormatCapability, ...]
    supports_resize: bool = False
    supports_quality: bool = False
    supports_alpha: bool = False
    supports_print_options: bool = False
    supports_ai_adapt: bool = False
    supports_batch_zip: bool = True
    max_batch_items: int = Field(default=500, ge=1, le=500)


class CreateExportItemRequest(ApiModel):
    artifact_version_id: UUID
    target_format: ExportFormat
    output_name: str = Field(min_length=1, max_length=240)


class CreateExportJobRequest(ApiModel):
    task_id: UUID
    items: tuple[CreateExportItemRequest, ...] = Field(min_length=1, max_length=500)
    force_zip: bool = False
    package_name: str = Field(default="export", min_length=1, max_length=240)


class ExportJobItemResponse(ApiModel):
    artifact_version_id: UUID
    target_format: ExportFormat
    output_name: str


class ExportOutputResponse(ApiModel):
    name: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    renderer_version: str
    source_artifact_id: UUID
    source_artifact_version_id: UUID


class ExportManifestEntryResponse(ApiModel):
    name: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: UUID
    artifact_version_id: UUID
    renderer_version: str


class ExportManifestResponse(ApiModel):
    schema_version: str
    export_job_id: UUID
    operation_id: UUID
    created_at: datetime
    exporter_version: str
    entries: tuple[ExportManifestEntryResponse, ...]


class ExportPackageResponse(ApiModel):
    package_id: UUID
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    is_archive: bool


class ExportJobResponse(ApiModel):
    job_id: UUID
    project_id: UUID
    task_id: UUID
    operation_id: UUID
    status: ExportJobStatus
    items: tuple[ExportJobItemResponse, ...]
    outputs: tuple[ExportOutputResponse, ...]
    package: ExportPackageResponse | None = None
    manifest: ExportManifestResponse | None = None
    error_code: str | None = Field(default=None, max_length=240)


class ExportDownloadGrantResponse(ApiModel):
    job_id: UUID
    package_id: UUID
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    url: str = Field(min_length=1)


class ExportTaskCreateResponse(ApiModel):
    task_id: UUID
    task_version: int = Field(ge=1)
