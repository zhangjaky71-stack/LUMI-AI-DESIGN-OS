from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from lumi_asset_storage import SignedUpload

from lumi_api.api.v1.context import RequestContext, require_idempotency_key
from lumi_api.api.v1.errors import ApiProblem
from lumi_api.projects.security import get_secure_project_context

from .errors import (
    AssetNotFound,
    AssetStorageConflict,
    AssetStorageError,
    AssetStorageInvalid,
    UploadSessionNotFound,
)
from .runtime import AssetStorageRuntime
from .schemas import (
    CompleteAssetUploadRequest,
    CompleteAssetUploadResponse,
    CreateAssetUploadRequest,
    CreateAssetUploadResponse,
    SignUploadPartRequest,
    SignUploadPartResponse,
    SignedAssetDownloadResponse,
    SignedPutResource,
)
from .service import AssetStorageService

ContextDep = Annotated[RequestContext, Depends(get_secure_project_context)]
IdempotencyDep = Annotated[str, Depends(require_idempotency_key)]


def create_asset_storage_router(runtime: AssetStorageRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["assets"])

    def service(session) -> AssetStorageService:
        return AssetStorageService(
            session,
            object_store=runtime.object_store,
            bucket=runtime.bucket,
            presign_ttl_seconds=runtime.presign_ttl_seconds,
            download_ttl_seconds=runtime.download_ttl_seconds,
            max_file_bytes=runtime.max_file_bytes,
            max_org_storage_bytes=runtime.max_org_storage_bytes,
            multipart_threshold_bytes=runtime.multipart_threshold_bytes,
        )

    @router.post(
        "/assets:create-upload",
        operation_id="createAssetUpload",
        response_model=CreateAssetUploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_upload(
        payload: CreateAssetUploadRequest,
        context: ContextDep,
        idempotency_key: IdempotencyDep,
    ) -> CreateAssetUploadResponse:
        actor_id = _actor(context)
        failure: ApiProblem | None = None
        result = None
        async with runtime.session_factory() as session, session.begin():
            try:
                result = await service(session).create_upload(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    idempotency_key=idempotency_key,
                    project_id=payload.project_id,
                    original_name=payload.original_name,
                    declared_mime_type=payload.declared_mime_type,
                    declared_size=payload.declared_size,
                    checksum_sha256=payload.checksum_sha256,
                    rights_assertion=payload.rights_assertion,
                    source_reference=payload.source_reference,
                    upload_mode=payload.upload_mode,
                )
            except AssetStorageError as exc:
                failure = _problem(exc)
        if failure is not None:
            raise failure
        assert result is not None
        asset, upload, grant = result
        signed = None
        if isinstance(grant, SignedUpload):
            signed = SignedPutResource(
                url=grant.url,
                required_headers=grant.required_headers,
                expires_at=grant.expires_at,
            )
        return CreateAssetUploadResponse(
            asset_id=asset.id,
            upload_session_id=upload.id,
            file_id=upload.file_id,
            upload_mode=upload.upload_mode,
            status=upload.status,
            upload=signed,
            expires_at=upload.expires_at,
        )

    @router.post(
        "/asset-uploads/{upload_session_id}/parts/{part_number}:sign",
        operation_id="signAssetUploadPart",
        response_model=SignUploadPartResponse,
    )
    async def sign_part(
        upload_session_id: UUID,
        part_number: int,
        payload: SignUploadPartRequest,
        context: ContextDep,
    ) -> SignUploadPartResponse:
        failure: ApiProblem | None = None
        signed = None
        async with runtime.session_factory() as session, session.begin():
            try:
                signed = await service(session).sign_multipart_part(
                    organization_id=context.organization_id,
                    upload_session_id=upload_session_id,
                    part_number=part_number,
                    checksum_sha256=payload.checksum_sha256,
                )
            except AssetStorageError as exc:
                failure = _problem(exc)
        if failure is not None:
            raise failure
        assert signed is not None
        return SignUploadPartResponse(
            part_number=signed.part_number,
            url=signed.url,
            required_headers=signed.required_headers,
            expires_at=signed.expires_at,
        )

    @router.post(
        "/asset-uploads/{upload_session_id}:complete",
        operation_id="completeAssetUpload",
        response_model=CompleteAssetUploadResponse,
    )
    async def complete_upload(
        upload_session_id: UUID,
        payload: CompleteAssetUploadRequest,
        context: ContextDep,
    ) -> CompleteAssetUploadResponse:
        actor_id = _actor(context)
        failure: ApiProblem | None = None
        result = None
        async with runtime.session_factory() as session, session.begin():
            try:
                result = await service(session).complete_upload(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    upload_session_id=upload_session_id,
                    parts=tuple(
                        (part.part_number, part.etag, part.checksum_sha256)
                        for part in payload.parts
                    ),
                )
            except AssetStorageError as exc:
                failure = _problem(exc)
        if failure is not None:
            raise failure
        assert result is not None
        asset, upload, validation = result
        return CompleteAssetUploadResponse(
            asset_id=asset.id,
            upload_session_id=upload.id,
            validation_run_id=validation.id,
        )

    @router.post(
        "/asset-uploads/{upload_session_id}:abort",
        operation_id="abortAssetUpload",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def abort_upload(
        upload_session_id: UUID,
        context: ContextDep,
    ) -> None:
        actor_id = _actor(context)
        failure: ApiProblem | None = None
        async with runtime.session_factory() as session, session.begin():
            try:
                await service(session).abort_upload(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    upload_session_id=upload_session_id,
                )
            except AssetStorageError as exc:
                failure = _problem(exc)
        if failure is not None:
            raise failure

    @router.get(
        "/assets/{asset_id}:download",
        operation_id="getAssetSignedDownload",
        response_model=SignedAssetDownloadResponse,
    )
    async def signed_download(
        asset_id: UUID,
        context: ContextDep,
        variant: Annotated[str, Query(min_length=1, max_length=64)] = "original",
    ) -> SignedAssetDownloadResponse:
        failure: ApiProblem | None = None
        result = None
        async with runtime.session_factory() as session, session.begin():
            try:
                result = await service(session).signed_download(
                    organization_id=context.organization_id,
                    asset_id=asset_id,
                    variant=variant,
                )
            except AssetStorageError as exc:
                failure = _problem(exc)
        if failure is not None:
            raise failure
        assert result is not None
        file, signed = result
        return SignedAssetDownloadResponse(
            asset_id=asset_id,
            variant=file.variant,
            url=signed.url,
            expires_at=signed.expires_at,
        )

    return router


def _actor(context: RequestContext) -> UUID:
    if context.actor_id is None:
        raise ApiProblem(status=403, code="PERMISSION_DENIED", title="Permission denied")
    return context.actor_id


def _problem(error: AssetStorageError) -> ApiProblem:
    if isinstance(error, (AssetNotFound, UploadSessionNotFound)):
        return ApiProblem(status=404, code=error.code, title="Resource not found")
    if isinstance(error, AssetStorageConflict):
        return ApiProblem(
            status=409,
            code=error.code,
            title="Asset storage conflict",
            detail=str(error),
        )
    if isinstance(error, AssetStorageInvalid):
        return ApiProblem(
            status=422,
            code=error.code,
            title="Invalid asset request",
            detail=str(error),
        )
    return ApiProblem(status=500, code="ASSET_STORAGE_FAILED", title="Asset storage failed")
