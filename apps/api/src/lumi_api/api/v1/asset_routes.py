from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, status

from lumi_api.assets.api import (
    AssetDownloadResponse,
    AssetPreviewListResponse,
    AssetResponse,
    CompleteAssetUploadRequest,
    CreateAssetUploadRequest,
    CreateAssetUploadResponse,
    MultipartPartResponse,
)

from .asset_dependencies import AssetServiceDependency
from .common import ProblemDetail
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


@router.post(
    "/projects/{project_id}/assets/uploads",
    response_model=CreateAssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["assets"],
)
async def create_asset_upload(
    project_id: UUID,
    request: CreateAssetUploadRequest,
    organization_id: OrganizationId,
    service: AssetServiceDependency,
) -> CreateAssetUploadResponse:
    return await service.create_upload(organization_id, project_id, request)


@router.post(
    "/assets/uploads/{upload_id}/parts/{part_number}",
    response_model=MultipartPartResponse,
    responses=_ERROR_RESPONSES,
    tags=["assets"],
)
async def sign_asset_upload_part(
    upload_id: UUID,
    part_number: Annotated[int, Path(ge=1, le=10_000)],
    organization_id: OrganizationId,
    service: AssetServiceDependency,
) -> MultipartPartResponse:
    return await service.sign_multipart_part(organization_id, upload_id, part_number)


@router.post(
    "/assets/uploads/{upload_id}/complete",
    response_model=AssetResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["assets"],
)
async def complete_asset_upload(
    upload_id: UUID,
    request: CompleteAssetUploadRequest,
    organization_id: OrganizationId,
    service: AssetServiceDependency,
) -> AssetResponse:
    return await service.complete_upload(organization_id, upload_id, request)


@router.get(
    "/assets/{asset_id}",
    response_model=AssetResponse,
    responses=_ERROR_RESPONSES,
    tags=["assets"],
)
async def get_asset(
    asset_id: UUID,
    organization_id: OrganizationId,
    service: AssetServiceDependency,
) -> AssetResponse:
    return await service.get_asset(organization_id, asset_id)


@router.get(
    "/assets/{asset_id}/download",
    response_model=AssetDownloadResponse,
    responses=_ERROR_RESPONSES,
    tags=["assets"],
)
async def get_asset_download(
    asset_id: UUID,
    organization_id: OrganizationId,
    service: AssetServiceDependency,
) -> AssetDownloadResponse:
    return await service.get_download(organization_id, asset_id)


@router.get(
    "/assets/{asset_id}/previews",
    response_model=AssetPreviewListResponse,
    responses=_ERROR_RESPONSES,
    tags=["assets"],
)
async def list_asset_previews(
    asset_id: UUID,
    organization_id: OrganizationId,
    service: AssetServiceDependency,
) -> AssetPreviewListResponse:
    return await service.list_previews(organization_id, asset_id)
