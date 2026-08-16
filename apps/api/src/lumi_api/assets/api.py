from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_api.auth import Principal

from .models import AssetFileRole, AssetRecord, AssetStatus, RightsAssertion, SignedRequest
from .service import AssetStorageService, CompleteUploadCommand, CreateUploadCommand


class AssetApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignedRequestResponse(AssetApiModel):
    method: str
    url: str
    expires_at: datetime
    headers: dict[str, str] = Field(default_factory=dict)


class CreateAssetUploadRequest(AssetApiModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(ge=1)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rights_assertion: RightsAssertion
    rights_source_uri: str | None = Field(default=None, max_length=2_000)


class CreateAssetUploadResponse(AssetApiModel):
    asset_id: UUID
    upload_id: UUID
    status: AssetStatus
    upload_mode: str
    upload_request: SignedRequestResponse | None = None
    multipart_upload_id: str | None = None
    expires_at: datetime


class MultipartPartResponse(AssetApiModel):
    part_number: int = Field(ge=1, le=10_000)
    request: SignedRequestResponse


class MultipartCompletedPart(AssetApiModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=255)


class CompleteAssetUploadRequest(AssetApiModel):
    parts: tuple[MultipartCompletedPart, ...] = ()


class AssetResponse(AssetApiModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    original_filename: str
    declared_mime_type: str
    mime_type: str | None = None
    media_kind: str | None = None
    status: AssetStatus
    rights_assertion: RightsAssertion
    rejected_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class AssetFileResponse(AssetApiModel):
    id: UUID
    role: AssetFileRole
    mime_type: str
    byte_size: int
    checksum_sha256: str
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None


class AssetPreviewListResponse(AssetApiModel):
    asset_id: UUID
    items: tuple[AssetFileResponse, ...]


class AssetDownloadResponse(AssetApiModel):
    asset_id: UUID
    request: SignedRequestResponse


class AssetApiService(Protocol):
    async def create_upload(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: CreateAssetUploadRequest,
    ) -> CreateAssetUploadResponse: ...

    async def sign_multipart_part(
        self,
        organization_id: UUID,
        upload_id: UUID,
        part_number: int,
    ) -> MultipartPartResponse: ...

    async def complete_upload(
        self,
        organization_id: UUID,
        upload_id: UUID,
        request: CompleteAssetUploadRequest,
    ) -> AssetResponse: ...

    async def get_asset(self, organization_id: UUID, asset_id: UUID) -> AssetResponse: ...

    async def get_download(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetDownloadResponse: ...

    async def list_previews(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetPreviewListResponse: ...


def _signed_response(request: SignedRequest) -> SignedRequestResponse:
    return SignedRequestResponse(
        method=request.method,
        url=request.url,
        expires_at=request.expires_at,
        headers=request.headers,
    )


class AssetApiAdapter(AssetApiService):
    def __init__(self, service: AssetStorageService, *, principal: Principal) -> None:
        self.service = service
        self.principal = principal

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _asset_response(asset: AssetRecord) -> AssetResponse:
        return AssetResponse(
            id=asset.id,
            organization_id=asset.organization_id,
            project_id=asset.project_id,
            original_filename=asset.original_filename,
            declared_mime_type=asset.declared_mime_type,
            mime_type=asset.mime_type,
            media_kind=asset.media_kind.value if asset.media_kind else None,
            status=asset.status,
            rights_assertion=asset.rights_assertion,
            rejected_reason=asset.rejected_reason,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    async def create_upload(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: CreateAssetUploadRequest,
    ) -> CreateAssetUploadResponse:
        grant = self.service.create_upload(
            CreateUploadCommand(
                organization_id=organization_id,
                project_id=project_id,
                filename=request.filename,
                declared_mime_type=request.content_type,
                expected_size=request.byte_size,
                expected_checksum_sha256=request.checksum_sha256,
                rights_assertion=request.rights_assertion,
                rights_source_uri=request.rights_source_uri,
                actor=self.principal,
                now=self._now(),
            )
        )
        return CreateAssetUploadResponse(
            asset_id=grant.asset.id,
            upload_id=grant.upload.id,
            status=grant.asset.status,
            upload_mode=grant.upload.mode.value,
            upload_request=_signed_response(grant.request) if grant.request else None,
            multipart_upload_id=grant.multipart_upload_id,
            expires_at=grant.upload.expires_at,
        )

    async def sign_multipart_part(
        self,
        organization_id: UUID,
        upload_id: UUID,
        part_number: int,
    ) -> MultipartPartResponse:
        signed = self.service.sign_multipart_part(
            organization_id,
            upload_id,
            part_number=part_number,
            actor=self.principal,
            now=self._now(),
        )
        return MultipartPartResponse(part_number=part_number, request=_signed_response(signed))

    async def complete_upload(
        self,
        organization_id: UUID,
        upload_id: UUID,
        request: CompleteAssetUploadRequest,
    ) -> AssetResponse:
        asset = self.service.complete_upload(
            CompleteUploadCommand(
                organization_id=organization_id,
                upload_id=upload_id,
                actor=self.principal,
                now=self._now(),
                multipart_parts=tuple((part.part_number, part.etag) for part in request.parts),
            )
        )
        return self._asset_response(asset)

    async def get_asset(self, organization_id: UUID, asset_id: UUID) -> AssetResponse:
        return self._asset_response(
            self.service.get_asset(organization_id, asset_id, actor=self.principal)
        )

    async def get_download(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetDownloadResponse:
        signed = self.service.signed_download(
            organization_id,
            asset_id,
            actor=self.principal,
            now=self._now(),
        )
        return AssetDownloadResponse(asset_id=asset_id, request=_signed_response(signed))

    async def list_previews(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetPreviewListResponse:
        self.service.get_asset(organization_id, asset_id, actor=self.principal)
        previews = self.service.repository.list_previews(organization_id, asset_id)
        return AssetPreviewListResponse(
            asset_id=asset_id,
            items=tuple(
                AssetFileResponse(
                    id=item.file.id,
                    role=item.file.role,
                    mime_type=item.file.mime_type,
                    byte_size=item.file.byte_size,
                    checksum_sha256=item.file.checksum_sha256,
                    width=item.file.width,
                    height=item.file.height,
                    duration_ms=item.file.duration_ms,
                )
                for item in previews
            ),
        )
