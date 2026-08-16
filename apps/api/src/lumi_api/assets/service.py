from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from lumi_api.auth import AccessPolicyService, Permission, Principal
from lumi_api.domain.ids import new_uuid7

from .models import (
    AssetAuditEntry,
    AssetEvent,
    AssetEventType,
    AssetFileRecord,
    AssetFileRole,
    AssetPreview,
    AssetRecord,
    AssetStatus,
    QuotaPolicy,
    RightsAssertion,
    ScanStatus,
    SignedRequest,
    UploadMode,
    UploadSession,
    UploadStatus,
    ValidationReport,
)
from .object_store import ObjectStore, UploadIntent
from .preview import NoopPreviewRenderer, PreviewRenderer
from .security import (
    FileScanner,
    MetadataExtractor,
    SUPPORTED_MIME_KIND,
    SafeMetadataExtractor,
    UnavailableFileScanner,
    sanitize_filename,
    sanitize_svg,
    sniff_mime,
)
from .store import AssetRepository


class AssetStorageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateUploadCommand:
    organization_id: UUID
    project_id: UUID
    filename: str
    declared_mime_type: str
    expected_size: int
    expected_checksum_sha256: str
    rights_assertion: RightsAssertion
    actor: Principal
    now: object
    rights_source_uri: str | None = None


@dataclass(frozen=True, slots=True)
class UploadGrant:
    asset: AssetRecord
    upload: UploadSession
    request: SignedRequest | None
    multipart_upload_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompleteUploadCommand:
    organization_id: UUID
    upload_id: UUID
    actor: Principal
    now: object
    multipart_parts: tuple[tuple[int, str], ...] = ()


class AssetStorageService:
    def __init__(
        self,
        repository: AssetRepository,
        object_store: ObjectStore,
        *,
        bucket: str = "lumi-assets",
        policy: AccessPolicyService | None = None,
        quota: QuotaPolicy | None = None,
        scanner: FileScanner | None = None,
        metadata_extractor: MetadataExtractor | None = None,
        preview_renderer: PreviewRenderer | None = None,
    ) -> None:
        self.repository = repository
        self.object_store = object_store
        self.bucket = bucket
        self.policy = policy or AccessPolicyService()
        self.quota = quota or QuotaPolicy()
        self.scanner = scanner or UnavailableFileScanner()
        self.metadata_extractor = metadata_extractor or SafeMetadataExtractor()
        self.preview_renderer = preview_renderer or NoopPreviewRenderer()

    def _authorize(self, actor: Principal, organization_id: UUID, permission: Permission) -> None:
        decision = self.policy.authorize(actor, organization_id=organization_id, permission=permission)
        if not decision.allowed:
            raise AssetStorageError(decision.reason_code)

    @staticmethod
    def _key(
        organization_id: UUID,
        project_id: UUID,
        asset_id: UUID,
        file_id: UUID,
        role: AssetFileRole,
    ) -> str:
        return (
            f"org/{organization_id}/project/{project_id}/asset/{asset_id}/"
            f"{role.value}/{file_id}"
        )

    def create_upload(self, command: CreateUploadCommand) -> UploadGrant:
        from datetime import datetime

        if not isinstance(command.now, datetime):
            raise TypeError("now must be datetime")
        self._authorize(command.actor, command.organization_id, Permission.ASSET_UPLOAD)
        if not self.repository.project_exists(command.organization_id, command.project_id):
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        if command.declared_mime_type not in SUPPORTED_MIME_KIND:
            raise AssetStorageError("DECLARED_MEDIA_TYPE_NOT_SUPPORTED")
        if not 1 <= command.expected_size <= self.quota.max_file_bytes:
            raise AssetStorageError("UPLOAD_FILE_SIZE_LIMIT_EXCEEDED")
        projected_usage = self.repository.current_verified_usage(command.organization_id) + command.expected_size
        if projected_usage > self.quota.max_org_storage_bytes:
            raise AssetStorageError("ORGANIZATION_STORAGE_QUOTA_EXCEEDED")
        filename = sanitize_filename(command.filename)
        asset_id = new_uuid7()
        file_id = new_uuid7()
        upload_id = new_uuid7()
        key = self._key(
            command.organization_id,
            command.project_id,
            asset_id,
            file_id,
            AssetFileRole.ORIGINAL,
        )
        mode = (
            UploadMode.MULTIPART
            if command.expected_size >= self.quota.multipart_threshold_bytes
            else UploadMode.SINGLE_PUT
        )
        asset = AssetRecord(
            id=asset_id,
            organization_id=command.organization_id,
            project_id=command.project_id,
            original_filename=filename,
            declared_mime_type=command.declared_mime_type,
            status=AssetStatus.UPLOADING,
            rights_assertion=command.rights_assertion,
            rights_source_uri=command.rights_source_uri,
            created_by=command.actor.user_id,
            created_at=command.now,
            updated_at=command.now,
        )
        intent = UploadIntent(
            bucket=self.bucket,
            key=key,
            expected_checksum_sha256=command.expected_checksum_sha256,
            declared_mime_type=command.declared_mime_type,
            expires_seconds=self.quota.upload_ttl_seconds,
        )
        request: SignedRequest | None
        storage_upload_id: str | None = None
        if mode is UploadMode.MULTIPART:
            storage_upload_id = self.object_store.start_multipart(intent, now=command.now)
            request = None
        else:
            request = self.object_store.create_upload(intent, now=command.now)
        upload = UploadSession(
            id=upload_id,
            organization_id=command.organization_id,
            project_id=command.project_id,
            asset_id=asset_id,
            file_id=file_id,
            bucket=self.bucket,
            object_key=key,
            original_filename=filename,
            declared_mime_type=command.declared_mime_type,
            expected_size=command.expected_size,
            expected_checksum_sha256=command.expected_checksum_sha256,
            mode=mode,
            storage_upload_id=storage_upload_id,
            created_at=command.now,
            expires_at=command.now + timedelta(seconds=self.quota.upload_ttl_seconds),
        )
        event = AssetEvent(
            organization_id=command.organization_id,
            project_id=command.project_id,
            asset_id=asset.id,
            event_type=AssetEventType.UPLOAD_CREATED,
            occurred_at=command.now,
            actor_id=command.actor.actor_id,
            payload={"upload_id": str(upload.id), "mode": mode.value},
        )
        audit = AssetAuditEntry(
            organization_id=command.organization_id,
            asset_id=asset.id,
            action="asset.upload.created",
            actor_id=command.actor.actor_id,
            occurred_at=command.now,
            details={"project_id": str(command.project_id), "filename": filename},
        )
        self.repository.insert_upload_bundle(asset, upload, event=event, audit=audit)
        return UploadGrant(asset=asset, upload=upload, request=request, multipart_upload_id=storage_upload_id)

    def sign_multipart_part(
        self,
        organization_id: UUID,
        upload_id: UUID,
        *,
        part_number: int,
        actor: Principal,
        now: object,
    ) -> SignedRequest:
        from datetime import datetime

        if not isinstance(now, datetime):
            raise TypeError("now must be datetime")
        self._authorize(actor, organization_id, Permission.ASSET_UPLOAD)
        upload = self.repository.get_upload(organization_id, upload_id)
        if upload is None:
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        if upload.mode is not UploadMode.MULTIPART or not upload.storage_upload_id:
            raise AssetStorageError("UPLOAD_NOT_MULTIPART")
        if now >= upload.expires_at:
            raise AssetStorageError("UPLOAD_EXPIRED")
        intent = UploadIntent(
            bucket=upload.bucket,
            key=upload.object_key,
            expected_checksum_sha256=upload.expected_checksum_sha256,
            declared_mime_type=upload.declared_mime_type,
            expires_seconds=self.quota.upload_ttl_seconds,
        )
        return self.object_store.sign_part(
            intent,
            upload_id=upload.storage_upload_id,
            part_number=part_number,
            now=now,
        )

    def complete_upload(self, command: CompleteUploadCommand) -> AssetRecord:
        from datetime import datetime

        if not isinstance(command.now, datetime):
            raise TypeError("now must be datetime")
        self._authorize(command.actor, command.organization_id, Permission.ASSET_UPLOAD)
        upload = self.repository.get_upload(command.organization_id, command.upload_id)
        if upload is None:
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        if upload.status not in {UploadStatus.PENDING, UploadStatus.UPLOADED}:
            raise AssetStorageError("UPLOAD_STATE_CONFLICT")
        if command.now >= upload.expires_at:
            raise AssetStorageError("UPLOAD_EXPIRED")
        intent = UploadIntent(
            bucket=upload.bucket,
            key=upload.object_key,
            expected_checksum_sha256=upload.expected_checksum_sha256,
            declared_mime_type=upload.declared_mime_type,
            expires_seconds=self.quota.upload_ttl_seconds,
        )
        if upload.mode is UploadMode.MULTIPART:
            if not upload.storage_upload_id or not command.multipart_parts:
                raise AssetStorageError("MULTIPART_COMPLETION_DATA_REQUIRED")
            self.object_store.complete_multipart(
                intent,
                upload_id=upload.storage_upload_id,
                parts=command.multipart_parts,
                now=command.now,
            )
        head = self.object_store.head(upload.bucket, upload.object_key, now=command.now)
        if not head.exists:
            raise AssetStorageError("UPLOADED_OBJECT_NOT_FOUND")
        if head.byte_size != upload.expected_size:
            raise AssetStorageError("UPLOADED_OBJECT_SIZE_MISMATCH")
        if head.checksum_sha256 and head.checksum_sha256 != upload.expected_checksum_sha256:
            raise AssetStorageError("UPLOADED_OBJECT_CHECKSUM_MISMATCH")
        current_asset = self.repository.get_asset(command.organization_id, upload.asset_id)
        if current_asset is None:
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        asset = current_asset.model_copy(
            update={"status": AssetStatus.VERIFYING, "updated_at": command.now}
        )
        completed = upload.model_copy(
            update={"status": UploadStatus.VERIFYING, "completed_at": command.now}
        )
        event = AssetEvent(
            organization_id=upload.organization_id,
            project_id=upload.project_id,
            asset_id=upload.asset_id,
            event_type=AssetEventType.UPLOAD_COMPLETED,
            occurred_at=command.now,
            actor_id=command.actor.actor_id,
            payload={"upload_id": str(upload.id), "verified_size": head.byte_size},
        )
        audit = AssetAuditEntry(
            organization_id=upload.organization_id,
            asset_id=upload.asset_id,
            action="asset.upload.completed",
            actor_id=command.actor.actor_id,
            occurred_at=command.now,
            details={"upload_id": str(upload.id)},
        )
        self.repository.mark_upload_complete(asset, completed, event=event, audit=audit)
        return asset

    def validate_upload(
        self,
        organization_id: UUID,
        upload_id: UUID,
        *,
        now: object,
    ) -> ValidationReport:
        from datetime import datetime

        if not isinstance(now, datetime):
            raise TypeError("now must be datetime")
        upload = self.repository.get_upload(organization_id, upload_id)
        if upload is None:
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        if upload.status is not UploadStatus.VERIFYING:
            raise AssetStorageError("UPLOAD_NOT_READY_FOR_VALIDATION")
        asset = self.repository.get_asset(organization_id, upload.asset_id)
        if asset is None:
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        digest = hashlib.sha256()
        actual_size = 0
        prefix = bytearray()
        with tempfile.NamedTemporaryFile(prefix="lumi-asset-", delete=True) as handle:
            for chunk in self.object_store.iter_bytes(upload.bucket, upload.object_key, now=now):
                digest.update(chunk)
                actual_size += len(chunk)
                if len(prefix) < 65_536:
                    prefix.extend(chunk[: 65_536 - len(prefix)])
                handle.write(chunk)
                if actual_size > self.quota.max_file_bytes:
                    return self._reject(
                        asset,
                        upload,
                        now=now,
                        actual_checksum=digest.hexdigest(),
                        actual_size=actual_size,
                        mime_type="application/octet-stream",
                        reason="UPLOAD_FILE_SIZE_LIMIT_EXCEEDED",
                    )
            handle.flush()
            actual_checksum = digest.hexdigest()
            if actual_size != upload.expected_size:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type="application/octet-stream",
                    reason="UPLOADED_OBJECT_SIZE_MISMATCH",
                )
            if actual_checksum != upload.expected_checksum_sha256:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type="application/octet-stream",
                    reason="UPLOADED_OBJECT_CHECKSUM_MISMATCH",
                )
            try:
                sniffed_mime, media_kind = sniff_mime(bytes(prefix))
            except ValueError as exc:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type="application/octet-stream",
                    reason=str(exc),
                )
            if sniffed_mime not in SUPPORTED_MIME_KIND:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type=sniffed_mime,
                    reason="SNIFFED_MEDIA_TYPE_NOT_SUPPORTED",
                )
            scan = self.scanner.scan(Path(handle.name))
            if scan.status is ScanStatus.INFECTED:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type=sniffed_mime,
                    reason="MALWARE_DETECTED",
                    scan=scan,
                )
            if self.quota.require_scanner and scan.status is not ScanStatus.CLEAN:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type=sniffed_mime,
                    reason="SCAN_UNAVAILABLE_OR_FAILED",
                    scan=scan,
                )
            try:
                metadata = self.metadata_extractor.extract(
                    Path(handle.name), mime_type=sniffed_mime, prefix=bytes(prefix)
                )
            except (ValueError, OSError) as exc:
                return self._reject(
                    asset,
                    upload,
                    now=now,
                    actual_checksum=actual_checksum,
                    actual_size=actual_size,
                    mime_type=sniffed_mime,
                    reason=str(exc),
                    scan=scan,
                )
            extra_files: list[AssetFileRecord] = []
            if sniffed_mime == "image/svg+xml":
                try:
                    sanitized = sanitize_svg(Path(handle.name).read_bytes())
                except (ValueError, UnicodeError) as exc:
                    return self._reject(
                        asset,
                        upload,
                        now=now,
                        actual_checksum=actual_checksum,
                        actual_size=actual_size,
                        mime_type=sniffed_mime,
                        reason=str(exc),
                        scan=scan,
                    )
                safe_id = new_uuid7()
                safe_key = self._key(
                    upload.organization_id,
                    upload.project_id,
                    upload.asset_id,
                    safe_id,
                    AssetFileRole.SANITIZED,
                )
                safe_checksum = hashlib.sha256(sanitized).hexdigest()
                self.object_store.put_derived(
                    upload.bucket,
                    safe_key,
                    sanitized,
                    content_type="image/svg+xml",
                    checksum_sha256=safe_checksum,
                    now=now,
                )
                extra_files.append(
                    AssetFileRecord(
                        id=safe_id,
                        organization_id=upload.organization_id,
                        asset_id=upload.asset_id,
                        role=AssetFileRole.SANITIZED,
                        bucket=upload.bucket,
                        object_key=safe_key,
                        checksum_sha256=safe_checksum,
                        byte_size=len(sanitized),
                        mime_type="image/svg+xml",
                        verified_at=now,
                    )
                )
            original = AssetFileRecord(
                id=upload.file_id,
                organization_id=upload.organization_id,
                asset_id=upload.asset_id,
                role=AssetFileRole.ORIGINAL,
                bucket=upload.bucket,
                object_key=upload.object_key,
                checksum_sha256=actual_checksum,
                byte_size=actual_size,
                mime_type=sniffed_mime,
                width=metadata.get("width"),
                height=metadata.get("height"),
                duration_ms=metadata.get("duration_ms"),
                fps=metadata.get("fps"),
                codec=metadata.get("codec"),
                has_alpha=metadata.get("has_alpha"),
                metadata={key: value for key, value in metadata.items() if key not in {"width", "height", "duration_ms", "fps", "codec", "has_alpha"}},
                verified_at=now,
            )
            previews: list[AssetPreview] = []
            for rendered in self.preview_renderer.render(
                Path(handle.name), media_kind=media_kind, mime_type=sniffed_mime
            ):
                preview_id = new_uuid7()
                preview_key = self._key(
                    upload.organization_id,
                    upload.project_id,
                    upload.asset_id,
                    preview_id,
                    rendered.role,
                )
                preview_checksum = hashlib.sha256(rendered.content).hexdigest()
                self.object_store.put_derived(
                    upload.bucket,
                    preview_key,
                    rendered.content,
                    content_type=rendered.mime_type,
                    checksum_sha256=preview_checksum,
                    now=now,
                )
                preview_file = AssetFileRecord(
                    id=preview_id,
                    organization_id=upload.organization_id,
                    asset_id=upload.asset_id,
                    role=rendered.role,
                    bucket=upload.bucket,
                    object_key=preview_key,
                    checksum_sha256=preview_checksum,
                    byte_size=len(rendered.content),
                    mime_type=rendered.mime_type,
                    width=rendered.width,
                    height=rendered.height,
                    duration_ms=rendered.duration_ms,
                    verified_at=now,
                )
                extra_files.append(preview_file)
                previews.append(
                    AssetPreview(
                        organization_id=upload.organization_id,
                        asset_id=upload.asset_id,
                        source_file_id=original.id,
                        role=rendered.role,
                        file=preview_file,
                        created_at=now,
                    )
                )
        accepted_asset = asset.model_copy(
            update={
                "status": AssetStatus.READY,
                "mime_type": sniffed_mime,
                "media_kind": media_kind,
                "updated_at": now,
            }
        )
        completed = upload.model_copy(update={"status": UploadStatus.COMPLETED, "completed_at": now})
        report = ValidationReport(
            organization_id=upload.organization_id,
            asset_id=upload.asset_id,
            upload_session_id=upload.id,
            expected_checksum_sha256=upload.expected_checksum_sha256,
            actual_checksum_sha256=actual_checksum,
            expected_size=upload.expected_size,
            actual_size=actual_size,
            sniffed_mime_type=sniffed_mime,
            media_kind=media_kind,
            scan=scan,
            accepted=True,
            metadata=metadata,
            created_at=now,
        )
        events = [
            AssetEvent(
                organization_id=upload.organization_id,
                project_id=upload.project_id,
                asset_id=upload.asset_id,
                event_type=AssetEventType.READY,
                occurred_at=now,
                payload={"mime_type": sniffed_mime},
            )
        ]
        events.extend(
            AssetEvent(
                organization_id=upload.organization_id,
                project_id=upload.project_id,
                asset_id=upload.asset_id,
                event_type=AssetEventType.PREVIEW_CREATED,
                occurred_at=now,
                payload={"preview_id": str(preview.id), "role": preview.role.value},
            )
            for preview in previews
        )
        audit = AssetAuditEntry(
            organization_id=upload.organization_id,
            asset_id=upload.asset_id,
            action="asset.ready",
            occurred_at=now,
            details={"upload_id": str(upload.id), "mime_type": sniffed_mime},
        )
        self.repository.finalize_validation(
            accepted_asset,
            completed,
            report,
            (original, *extra_files),
            tuple(previews),
            events=tuple(events),
            audit=audit,
        )
        return report

    def _reject(
        self,
        asset: AssetRecord,
        upload: UploadSession,
        *,
        now: object,
        actual_checksum: str,
        actual_size: int,
        mime_type: str,
        reason: str,
        scan: object | None = None,
    ) -> ValidationReport:
        from datetime import datetime

        from .models import FileScanResult, MediaKind, ScanStatus

        if not isinstance(now, datetime):
            raise TypeError("now must be datetime")
        scan_result = (
            scan
            if isinstance(scan, FileScanResult)
            else FileScanResult(status=ScanStatus.UNAVAILABLE, engine="not-run")
        )
        try:
            _, media_kind = sniff_mime(mime_type.encode())
        except ValueError:
            media_kind = SUPPORTED_MIME_KIND.get(mime_type, MediaKind.DOCUMENT)
        rejected = asset.model_copy(
            update={
                "status": AssetStatus.REJECTED,
                "rejected_reason": reason,
                "updated_at": now,
            }
        )
        rejected_upload = upload.model_copy(
            update={"status": UploadStatus.REJECTED, "completed_at": now}
        )
        report = ValidationReport(
            organization_id=upload.organization_id,
            asset_id=upload.asset_id,
            upload_session_id=upload.id,
            expected_checksum_sha256=upload.expected_checksum_sha256,
            actual_checksum_sha256=actual_checksum,
            expected_size=upload.expected_size,
            actual_size=actual_size,
            sniffed_mime_type=mime_type,
            media_kind=media_kind,
            scan=scan_result,
            accepted=False,
            reason_codes=(reason,),
            created_at=now,
        )
        event_type = (
            AssetEventType.SCAN_FAILED
            if reason in {"MALWARE_DETECTED", "SCAN_UNAVAILABLE_OR_FAILED"}
            else AssetEventType.REJECTED
        )
        event = AssetEvent(
            organization_id=upload.organization_id,
            project_id=upload.project_id,
            asset_id=upload.asset_id,
            event_type=event_type,
            occurred_at=now,
            payload={"reason": reason},
        )
        audit = AssetAuditEntry(
            organization_id=upload.organization_id,
            asset_id=upload.asset_id,
            action="asset.rejected",
            occurred_at=now,
            details={"reason": reason},
        )
        self.repository.finalize_validation(
            rejected,
            rejected_upload,
            report,
            (),
            (),
            events=(event,),
            audit=audit,
        )
        self.object_store.delete_candidate(upload.bucket, upload.object_key, now=now)
        return report

    def get_asset(self, organization_id: UUID, asset_id: UUID, *, actor: Principal) -> AssetRecord:
        self._authorize(actor, organization_id, Permission.PROJECT_READ)
        asset = self.repository.get_asset(organization_id, asset_id)
        if asset is None:
            raise AssetStorageError("TENANT_RESOURCE_NOT_FOUND")
        return asset

    def signed_download(
        self,
        organization_id: UUID,
        asset_id: UUID,
        *,
        actor: Principal,
        now: object,
    ) -> SignedRequest:
        from datetime import datetime

        if not isinstance(now, datetime):
            raise TypeError("now must be datetime")
        asset = self.get_asset(organization_id, asset_id, actor=actor)
        if asset.status is not AssetStatus.READY:
            raise AssetStorageError("ASSET_NOT_READY")
        files = self.repository.list_files(organization_id, asset_id)
        preferred = next((file for file in files if file.role is AssetFileRole.SANITIZED), None)
        if preferred is None:
            preferred = next((file for file in files if file.role is AssetFileRole.ORIGINAL), None)
        if preferred is None:
            raise AssetStorageError("ASSET_FILE_NOT_FOUND")
        return self.object_store.get_signed_download(
            preferred.bucket,
            preferred.object_key,
            filename=asset.original_filename,
            expires_seconds=self.quota.download_ttl_seconds,
            now=now,
        )

    def cleanup_orphans(self, organization_id: UUID, *, before: object, now: object) -> int:
        from datetime import datetime

        if not isinstance(before, datetime) or not isinstance(now, datetime):
            raise TypeError("before/now must be datetime")
        count = 0
        for upload in self.repository.expired_uploads(organization_id, before=before):
            if upload.mode is UploadMode.MULTIPART and upload.storage_upload_id:
                intent = UploadIntent(
                    bucket=upload.bucket,
                    key=upload.object_key,
                    expected_checksum_sha256=upload.expected_checksum_sha256,
                    declared_mime_type=upload.declared_mime_type,
                    expires_seconds=self.quota.upload_ttl_seconds,
                )
                self.object_store.abort_multipart(
                    intent, upload_id=upload.storage_upload_id, now=now
                )
            self.object_store.delete_candidate(upload.bucket, upload.object_key, now=now)
            self.repository.expire_upload(upload, now=now)
            count += 1
        return count
