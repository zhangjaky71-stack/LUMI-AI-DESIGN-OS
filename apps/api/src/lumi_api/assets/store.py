from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .models import (
    AssetAuditEntry,
    AssetEvent,
    AssetFileRecord,
    AssetPreview,
    AssetRecord,
    AssetStatus,
    UploadSession,
    UploadStatus,
    ValidationReport,
)


class AssetRepository(Protocol):
    def project_exists(self, organization_id: UUID, project_id: UUID) -> bool: ...

    def current_verified_usage(self, organization_id: UUID) -> int: ...

    def get_asset(self, organization_id: UUID, asset_id: UUID) -> AssetRecord | None: ...

    def get_upload(self, organization_id: UUID, upload_id: UUID) -> UploadSession | None: ...

    def insert_upload_bundle(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        *,
        event: AssetEvent,
        audit: AssetAuditEntry,
    ) -> None: ...

    def mark_upload_complete(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        *,
        event: AssetEvent,
        audit: AssetAuditEntry,
    ) -> None: ...

    def finalize_validation(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        report: ValidationReport,
        files: tuple[AssetFileRecord, ...],
        previews: tuple[AssetPreview, ...],
        *,
        events: tuple[AssetEvent, ...],
        audit: AssetAuditEntry,
    ) -> None: ...

    def list_files(self, organization_id: UUID, asset_id: UUID) -> tuple[AssetFileRecord, ...]: ...

    def list_previews(self, organization_id: UUID, asset_id: UUID) -> tuple[AssetPreview, ...]: ...

    def expired_uploads(self, organization_id: UUID, *, before: datetime) -> tuple[UploadSession, ...]: ...

    def expire_upload(self, upload: UploadSession, *, now: datetime) -> None: ...


@dataclass(slots=True)
class MemoryAssetRepository(AssetRepository):
    projects: set[tuple[UUID, UUID]] = field(default_factory=set)
    assets: dict[UUID, AssetRecord] = field(default_factory=dict)
    uploads: dict[UUID, UploadSession] = field(default_factory=dict)
    files: dict[UUID, AssetFileRecord] = field(default_factory=dict)
    previews: dict[UUID, AssetPreview] = field(default_factory=dict)
    reports: list[ValidationReport] = field(default_factory=list)
    events: list[AssetEvent] = field(default_factory=list)
    audits: list[AssetAuditEntry] = field(default_factory=list)

    def project_exists(self, organization_id: UUID, project_id: UUID) -> bool:
        return (organization_id, project_id) in self.projects

    def current_verified_usage(self, organization_id: UUID) -> int:
        asset_ids = {
            asset.id for asset in self.assets.values() if asset.organization_id == organization_id
        }
        return sum(file.byte_size for file in self.files.values() if file.asset_id in asset_ids)

    def get_asset(self, organization_id: UUID, asset_id: UUID) -> AssetRecord | None:
        asset = self.assets.get(asset_id)
        if asset is None or asset.organization_id != organization_id:
            return None
        return asset

    def get_upload(self, organization_id: UUID, upload_id: UUID) -> UploadSession | None:
        upload = self.uploads.get(upload_id)
        if upload is None or upload.organization_id != organization_id:
            return None
        return upload

    def insert_upload_bundle(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        *,
        event: AssetEvent,
        audit: AssetAuditEntry,
    ) -> None:
        if asset.id in self.assets or upload.id in self.uploads:
            raise ValueError("ASSET_UPLOAD_ALREADY_EXISTS")
        self.assets[asset.id] = asset
        self.uploads[upload.id] = upload
        self.events.append(event)
        self.audits.append(audit)

    def mark_upload_complete(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        *,
        event: AssetEvent,
        audit: AssetAuditEntry,
    ) -> None:
        current = self.get_upload(upload.organization_id, upload.id)
        if current is None or current.status not in {UploadStatus.PENDING, UploadStatus.UPLOADED}:
            raise ValueError("UPLOAD_STATE_CONFLICT")
        self.assets[asset.id] = asset
        self.uploads[upload.id] = upload
        self.events.append(event)
        self.audits.append(audit)

    def finalize_validation(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        report: ValidationReport,
        files: tuple[AssetFileRecord, ...],
        previews: tuple[AssetPreview, ...],
        *,
        events: tuple[AssetEvent, ...],
        audit: AssetAuditEntry,
    ) -> None:
        if asset.status not in {AssetStatus.READY, AssetStatus.REJECTED}:
            raise ValueError("ASSET_FINAL_STATUS_REQUIRED")
        self.assets[asset.id] = asset
        self.uploads[upload.id] = upload
        self.reports.append(report)
        for file in files:
            self.files[file.id] = file
        for preview in previews:
            self.previews[preview.id] = preview
        self.events.extend(events)
        self.audits.append(audit)

    def list_files(self, organization_id: UUID, asset_id: UUID) -> tuple[AssetFileRecord, ...]:
        if self.get_asset(organization_id, asset_id) is None:
            return ()
        return tuple(file for file in self.files.values() if file.asset_id == asset_id)

    def list_previews(self, organization_id: UUID, asset_id: UUID) -> tuple[AssetPreview, ...]:
        if self.get_asset(organization_id, asset_id) is None:
            return ()
        return tuple(preview for preview in self.previews.values() if preview.asset_id == asset_id)

    def expired_uploads(self, organization_id: UUID, *, before: datetime) -> tuple[UploadSession, ...]:
        return tuple(
            upload
            for upload in self.uploads.values()
            if upload.organization_id == organization_id
            and upload.expires_at <= before
            and upload.status in {UploadStatus.PENDING, UploadStatus.UPLOADED}
        )

    def expire_upload(self, upload: UploadSession, *, now: datetime) -> None:
        self.uploads[upload.id] = upload.model_copy(
            update={"status": UploadStatus.EXPIRED, "completed_at": now}
        )
