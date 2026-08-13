from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from lumi_asset_storage import (
    CompletedPart,
    MultipartUpload,
    ObjectStore,
    UploadQuota,
    UploadRequest,
    asset_object_key,
    require_upload_allowed,
    require_verified_size_within_quota,
    rights_from_assertion,
    sanitize_download_filename,
    sha256_base64_to_hex,
    sha256_hex_to_base64,
    supported_mime_types,
)
from lumi_domain import new_uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import (
    Asset,
    AssetFile,
    AssetRights,
    AssetUploadSession,
    AssetValidationRun,
    AuditEvent,
    IdempotencyOperation,
    OutboxEvent,
    Project,
)

from .errors import (
    AssetNotFound,
    AssetStorageConflict,
    AssetStorageInvalid,
    UploadSessionNotFound,
)


class AssetStorageService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        object_store: ObjectStore,
        bucket: str,
        presign_ttl_seconds: int,
        download_ttl_seconds: int,
        max_file_bytes: int,
        max_org_storage_bytes: int,
        multipart_threshold_bytes: int,
    ) -> None:
        self.session = session
        self.object_store = object_store
        self.bucket = bucket
        self.presign_ttl_seconds = presign_ttl_seconds
        self.download_ttl_seconds = download_ttl_seconds
        self.max_file_bytes = max_file_bytes
        self.max_org_storage_bytes = max_org_storage_bytes
        self.multipart_threshold_bytes = multipart_threshold_bytes

    async def create_upload(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
        project_id: UUID,
        original_name: str,
        declared_mime_type: str,
        declared_size: int,
        checksum_sha256: str,
        rights_assertion: str,
        source_reference: str | None,
        upload_mode: str,
    ) -> tuple[Asset, AssetUploadSession, object | None]:
        project = await self._require_mutable_project(organization_id, project_id)
        del project
        normalized_mime = declared_mime_type.split(";", 1)[0].strip().lower()
        if normalized_mime not in supported_mime_types():
            raise AssetStorageInvalid("UNSUPPORTED_MEDIA_TYPE")
        checksum_hex = checksum_sha256.strip().lower()
        checksum_b64 = sha256_hex_to_base64(checksum_hex)
        quota = await self._quota(organization_id)
        try:
            require_upload_allowed(declared_size=declared_size, quota=quota)
        except ValueError as exc:
            raise AssetStorageInvalid(str(exc)) from exc
        if upload_mode not in {"single", "multipart"}:
            raise AssetStorageInvalid("UPLOAD_MODE_INVALID")
        if upload_mode == "single" and declared_size > self.multipart_threshold_bytes:
            raise AssetStorageInvalid("MULTIPART_REQUIRED")

        request_hash = self._request_hash(
            project_id=project_id,
            original_name=original_name,
            declared_mime_type=normalized_mime,
            declared_size=declared_size,
            checksum_sha256=checksum_hex,
            rights_assertion=rights_assertion,
            source_reference=source_reference,
            upload_mode=upload_mode,
        )
        existing_operation = await self.session.scalar(
            select(IdempotencyOperation).where(
                IdempotencyOperation.organization_id == organization_id,
                IdempotencyOperation.idempotency_key == idempotency_key,
            )
        )
        if existing_operation is not None:
            if (
                existing_operation.operation_type != "asset.create_upload"
                or existing_operation.request_hash != request_hash
            ):
                raise AssetStorageConflict("IDEMPOTENCY_KEY_REUSED")
            if not existing_operation.result_ref:
                raise AssetStorageConflict("IDEMPOTENT_OPERATION_IN_PROGRESS")
            try:
                session_id = UUID(existing_operation.result_ref)
            except ValueError as exc:
                raise AssetStorageConflict("IDEMPOTENCY_RESULT_INVALID") from exc
            upload = await self._get_upload(organization_id, session_id, lock=False)
            asset = await self._get_asset(organization_id, upload.asset_id)
            grant = await self._regenerate_grant(upload, checksum_b64)
            return asset, upload, grant

        asset_id = new_uuid7()
        file_id = new_uuid7()
        upload_session_id = new_uuid7()
        object_key = asset_object_key(
            organization_id=str(organization_id),
            project_id=str(project_id),
            asset_id=str(asset_id),
            variant="original",
            file_id=str(file_id),
        )
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.presign_ttl_seconds)
        asset = Asset(
            id=asset_id,
            organization_id=organization_id,
            project_id=project_id,
            kind=self._kind_from_mime(normalized_mime),
            source="upload",
            original_name=original_name,
            metadata_json={},
            status="uploading",
        )
        rights = rights_from_assertion(
            rights_assertion,
            asset_id=str(asset_id),
            organization_id=str(organization_id),
            source_reference=source_reference,
        )
        rights_row = AssetRights(
            id=new_uuid7(),
            organization_id=organization_id,
            asset_id=asset_id,
            scope="rights-v1",
            source=rights_assertion,
            attribution_required=bool(rights["attribution_required"]),
            policy_json=rights,
            source_type=str(rights["source_type"]),
            owner_assertion=rights["owner_assertion"],
            license_type=str(rights["license_type"]),
            commercial_use=str(rights["commercial_use"]),
            redistribution=str(rights["redistribution"]),
            training_use=str(rights["training_use"]),
            source_reference=rights["source_reference"],
            review_status=str(rights["review_status"]),
        )
        upload = AssetUploadSession(
            id=upload_session_id,
            organization_id=organization_id,
            project_id=project_id,
            asset_id=asset_id,
            file_id=file_id,
            created_by=actor_id,
            status="pending",
            upload_mode=upload_mode,
            bucket=self.bucket,
            object_key=object_key,
            declared_mime_type=normalized_mime,
            declared_size=declared_size,
            expected_checksum_sha256=checksum_hex,
            expires_at=expires_at,
        )
        operation = IdempotencyOperation(
            id=new_uuid7(),
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            operation_type="asset.create_upload",
            status="pending",
            request_hash=request_hash,
        )
        self.session.add_all([asset, rights_row, upload, operation])
        await self.session.flush()

        upload_request = UploadRequest(
            bucket=self.bucket,
            object_key=object_key,
            content_type=normalized_mime,
            checksum_sha256_b64=checksum_b64,
            content_length=declared_size,
            expires_seconds=self.presign_ttl_seconds,
            metadata={
                "lumi-asset-id": str(asset_id),
                "lumi-upload-session-id": str(upload_session_id),
            },
        )
        if upload_mode == "single":
            grant: object | None = await self.object_store.create_upload(upload_request)
        else:
            multipart = await self.object_store.create_multipart_upload(upload_request)
            upload.multipart_upload_id = multipart.upload_id
            grant = None

        operation.status = "completed"
        operation.result_ref = str(upload_session_id)
        self._event(
            organization_id=organization_id,
            asset_id=asset_id,
            name="asset.upload.requested",
            payload={
                "project_id": str(project_id),
                "upload_session_id": str(upload_session_id),
                "upload_mode": upload_mode,
                "declared_size": declared_size,
                "declared_mime_type": normalized_mime,
            },
        )
        self._audit(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            asset_id=asset_id,
            action="asset.upload.requested",
            metadata={"project_id": str(project_id), "upload_mode": upload_mode},
        )
        await self.session.flush()
        return asset, upload, grant

    async def sign_multipart_part(
        self,
        *,
        organization_id: UUID,
        upload_session_id: UUID,
        part_number: int,
        checksum_sha256: str | None,
    ):
        upload = await self._get_upload(organization_id, upload_session_id, lock=False)
        self._require_pending(upload)
        if upload.upload_mode != "multipart" or not upload.multipart_upload_id:
            raise AssetStorageInvalid("UPLOAD_NOT_MULTIPART")
        checksum_b64 = (
            sha256_hex_to_base64(checksum_sha256) if checksum_sha256 is not None else None
        )
        return await self.object_store.create_part_upload(
            MultipartUpload(
                upload_id=upload.multipart_upload_id,
                bucket=upload.bucket,
                object_key=upload.object_key,
            ),
            part_number=part_number,
            checksum_sha256_b64=checksum_b64,
            expires_seconds=self.presign_ttl_seconds,
        )

    async def complete_upload(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        upload_session_id: UUID,
        parts: tuple[tuple[int, str, str | None], ...],
    ) -> tuple[Asset, AssetUploadSession, AssetValidationRun]:
        upload = await self._get_upload(organization_id, upload_session_id, lock=True)
        asset = await self._get_asset(organization_id, upload.asset_id)
        if upload.status == "completed":
            existing = await self.session.scalar(
                select(AssetValidationRun)
                .where(
                    AssetValidationRun.organization_id == organization_id,
                    AssetValidationRun.asset_id == upload.asset_id,
                    AssetValidationRun.asset_file_id == upload.file_id,
                )
                .order_by(AssetValidationRun.created_at.desc())
            )
            if existing is None:
                raise AssetStorageConflict("VALIDATION_RUN_MISSING")
            return asset, upload, existing
        self._require_pending(upload)

        if upload.upload_mode == "multipart":
            if not upload.multipart_upload_id:
                raise AssetStorageConflict("MULTIPART_UPLOAD_ID_MISSING")
            completed_parts = tuple(
                CompletedPart(
                    part_number=number,
                    etag=etag,
                    checksum_sha256_b64=(
                        sha256_hex_to_base64(checksum) if checksum is not None else None
                    ),
                )
                for number, etag, checksum in parts
            )
            await self.object_store.complete_multipart_upload(
                MultipartUpload(
                    upload_id=upload.multipart_upload_id,
                    bucket=upload.bucket,
                    object_key=upload.object_key,
                ),
                parts=completed_parts,
                checksum_sha256_b64=None,
            )
        elif parts:
            raise AssetStorageInvalid("SINGLE_UPLOAD_MUST_NOT_INCLUDE_PARTS")

        head = await self.object_store.head(bucket=upload.bucket, object_key=upload.object_key)
        quota = await self._quota(organization_id)
        try:
            require_verified_size_within_quota(
                verified_size=head.content_length,
                declared_size=upload.declared_size,
                quota=quota,
            )
        except ValueError as exc:
            await self._reject_upload(upload, asset, str(exc))
            raise AssetStorageConflict(str(exc)) from exc

        head_content_type = (head.content_type or "").split(";", 1)[0].strip().lower()
        if head_content_type and head_content_type != upload.declared_mime_type:
            await self._reject_upload(upload, asset, "UPLOAD_CONTENT_TYPE_MISMATCH")
            raise AssetStorageConflict("UPLOAD_CONTENT_TYPE_MISMATCH")

        native_checksum_verified = False
        if upload.upload_mode == "single" and head.checksum_sha256_b64:
            try:
                native_checksum_hex = sha256_base64_to_hex(head.checksum_sha256_b64)
            except ValueError:
                native_checksum_hex = None
            if native_checksum_hex is not None:
                if native_checksum_hex != upload.expected_checksum_sha256:
                    await self._reject_upload(upload, asset, "UPLOAD_CHECKSUM_MISMATCH")
                    raise AssetStorageConflict("UPLOAD_CHECKSUM_MISMATCH")
                native_checksum_verified = True

        now = datetime.now(UTC)
        upload.status = "completed"
        upload.completed_at = now
        upload.verified_at = now
        upload.verified_size = head.content_length
        upload.verification_error_code = None
        asset.status = "scanning"
        asset.rejection_code = None
        validation = AssetValidationRun(
            id=new_uuid7(),
            organization_id=organization_id,
            project_id=upload.project_id,
            asset_id=asset.id,
            asset_file_id=upload.file_id,
            status="pending",
            metadata_json={
                "upload_session_id": str(upload.id),
                "native_checksum_verified": native_checksum_verified,
                "upload_mode": upload.upload_mode,
            },
        )
        self.session.add(validation)
        self._event(
            organization_id=organization_id,
            asset_id=asset.id,
            name="asset.upload.completed",
            payload={
                "project_id": str(upload.project_id),
                "upload_session_id": str(upload.id),
                "validation_run_id": str(validation.id),
                "native_checksum_verified": native_checksum_verified,
            },
        )
        self._event(
            organization_id=organization_id,
            asset_id=asset.id,
            name="asset.validation.requested",
            payload={
                "project_id": str(upload.project_id),
                "upload_session_id": str(upload.id),
                "validation_run_id": str(validation.id),
                "file_id": str(upload.file_id),
            },
        )
        self._audit(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            asset_id=asset.id,
            action="asset.upload.completed",
            metadata={"validation_run_id": str(validation.id)},
        )
        await self.session.flush()
        return asset, upload, validation

    async def abort_upload(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        upload_session_id: UUID,
    ) -> AssetUploadSession:
        upload = await self._get_upload(organization_id, upload_session_id, lock=True)
        asset = await self._get_asset(organization_id, upload.asset_id)
        if upload.status in {"aborted", "expired", "rejected"}:
            return upload
        if upload.status == "completed":
            raise AssetStorageConflict("UPLOAD_ALREADY_COMPLETED")
        if upload.upload_mode == "multipart" and upload.multipart_upload_id:
            await self.object_store.abort_multipart_upload(
                MultipartUpload(
                    upload_id=upload.multipart_upload_id,
                    bucket=upload.bucket,
                    object_key=upload.object_key,
                )
            )
        upload.status = "aborted"
        asset.status = "rejected"
        asset.rejection_code = "UPLOAD_ABORTED"
        self._event(
            organization_id=organization_id,
            asset_id=asset.id,
            name="asset.upload.aborted",
            payload={"upload_session_id": str(upload.id)},
        )
        self._audit(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            asset_id=asset.id,
            action="asset.upload.aborted",
            metadata={"upload_session_id": str(upload.id)},
        )
        await self.session.flush()
        return upload

    async def get_asset(self, *, organization_id: UUID, asset_id: UUID) -> Asset:
        return await self._get_asset(organization_id, asset_id)

    async def signed_download(
        self,
        *,
        organization_id: UUID,
        asset_id: UUID,
        variant: str,
    ):
        asset = await self._get_asset(organization_id, asset_id)
        if asset.status != "ready":
            raise AssetStorageConflict("ASSET_NOT_READY")
        file = await self.session.scalar(
            select(AssetFile).where(
                AssetFile.organization_id == organization_id,
                AssetFile.asset_id == asset_id,
                AssetFile.variant == variant,
            )
        )
        if file is None:
            raise AssetStorageInvalid("ASSET_VARIANT_NOT_FOUND")
        download_name = sanitize_download_filename(asset.original_name, fallback="asset")
        attachment = variant == "original" or file.mime_type == "image/svg+xml"
        return file, await self.object_store.get_signed_download(
            bucket=file.bucket,
            object_key=file.object_key,
            expires_seconds=self.download_ttl_seconds,
            download_name=download_name,
            attachment=attachment,
        )

    async def _quota(self, organization_id: UUID) -> UploadQuota:
        used = await self.session.scalar(
            select(func.coalesce(func.sum(AssetFile.byte_size), 0))
            .select_from(AssetFile)
            .join(Asset, Asset.id == AssetFile.asset_id)
            .where(
                AssetFile.organization_id == organization_id,
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        )
        return UploadQuota(
            max_file_bytes=self.max_file_bytes,
            max_org_storage_bytes=self.max_org_storage_bytes,
            current_org_storage_bytes=int(used or 0),
        )

    async def _require_mutable_project(self, organization_id: UUID, project_id: UUID) -> Project:
        project = await self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
        )
        if project is None:
            raise AssetStorageInvalid("PROJECT_NOT_FOUND_OR_FORBIDDEN")
        if project.status == "archived":
            raise AssetStorageConflict("PROJECT_ARCHIVED")
        return project

    async def _get_asset(self, organization_id: UUID, asset_id: UUID) -> Asset:
        asset = await self.session.scalar(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        )
        if asset is None:
            raise AssetNotFound()
        return asset

    async def _get_upload(
        self,
        organization_id: UUID,
        upload_session_id: UUID,
        *,
        lock: bool,
    ) -> AssetUploadSession:
        statement = select(AssetUploadSession).where(
            AssetUploadSession.id == upload_session_id,
            AssetUploadSession.organization_id == organization_id,
        )
        if lock:
            statement = statement.with_for_update()
        upload = await self.session.scalar(statement)
        if upload is None:
            raise UploadSessionNotFound()
        return upload

    def _require_pending(self, upload: AssetUploadSession) -> None:
        now = datetime.now(UTC)
        if upload.status != "pending":
            raise AssetStorageConflict("UPLOAD_NOT_PENDING")
        if upload.expires_at <= now:
            upload.status = "expired"
            raise AssetStorageConflict("UPLOAD_EXPIRED")

    async def _reject_upload(
        self,
        upload: AssetUploadSession,
        asset: Asset,
        code: str,
    ) -> None:
        upload.status = "rejected"
        upload.verification_error_code = code
        asset.status = "rejected"
        asset.rejection_code = code
        self._event(
            organization_id=upload.organization_id,
            asset_id=asset.id,
            name="asset.upload.rejected",
            payload={"upload_session_id": str(upload.id), "code": code},
        )
        await self.session.flush()

    async def _regenerate_grant(self, upload: AssetUploadSession, checksum_b64: str):
        if upload.status != "pending" or upload.expires_at <= datetime.now(UTC):
            return None
        if upload.upload_mode == "multipart":
            return None
        remaining = max(60, int((upload.expires_at - datetime.now(UTC)).total_seconds()))
        return await self.object_store.create_upload(
            UploadRequest(
                bucket=upload.bucket,
                object_key=upload.object_key,
                content_type=upload.declared_mime_type,
                checksum_sha256_b64=checksum_b64,
                content_length=upload.declared_size,
                expires_seconds=min(remaining, self.presign_ttl_seconds),
                metadata={
                    "lumi-asset-id": str(upload.asset_id),
                    "lumi-upload-session-id": str(upload.id),
                },
            )
        )

    def _event(
        self,
        *,
        organization_id: UUID,
        asset_id: UUID,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        self.session.add(
            OutboxEvent(
                id=new_uuid7(),
                organization_id=organization_id,
                event_name=name,
                aggregate_type="asset",
                aggregate_id=asset_id,
                schema_version=1,
                payload_json=payload,
            )
        )

    def _audit(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        asset_id: UUID,
        action: str,
        metadata: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditEvent(
                id=new_uuid7(),
                organization_id=organization_id,
                actor_type="user_or_service_token",
                actor_id=actor_id,
                action=action,
                target_type="asset",
                target_id=asset_id,
                request_id=request_id,
                metadata_json=metadata,
            )
        )

    @staticmethod
    def _kind_from_mime(mime: str) -> str:
        if mime.startswith("image/") and mime != "image/svg+xml":
            return "image"
        if mime == "image/svg+xml":
            return "vector"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("font/"):
            return "font"
        if mime == "application/pdf":
            return "document"
        return "file"

    @staticmethod
    def _request_hash(**payload: Any) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
