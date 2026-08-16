from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from lumi_api.assets.api import (
    AssetApiService,
    AssetDownloadResponse,
    AssetPreviewListResponse,
    AssetResponse,
    CompleteAssetUploadRequest,
    CreateAssetUploadRequest,
    CreateAssetUploadResponse,
    MultipartPartResponse,
)
from lumi_api.domain.ids import new_uuid7

JobKind = Literal[
    "image.transform",
    "video.render",
    "asset.preview",
    "asset.validate",
    "export.package",
]


class QueueContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JobScheduleRequest(QueueContractModel):
    job_id: UUID
    organization_id: UUID
    project_id: UUID
    job_kind: JobKind
    operation_id: UUID | None = None
    resource_id: UUID | None = None
    traceparent: str | None = None


class JobScheduler(Protocol):
    async def schedule(self, request: JobScheduleRequest) -> None: ...


class MemoryJobScheduler(JobScheduler):
    def __init__(self) -> None:
        self.requests: list[JobScheduleRequest] = []

    async def schedule(self, request: JobScheduleRequest) -> None:
        self.requests.append(request)


class QueuedAssetApiService(AssetApiService):
    """NODE-18 API wrapper that schedules validation after durable upload completion."""

    def __init__(self, delegate: AssetApiService, scheduler: JobScheduler) -> None:
        self.delegate = delegate
        self.scheduler = scheduler

    async def create_upload(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: CreateAssetUploadRequest,
    ) -> CreateAssetUploadResponse:
        return await self.delegate.create_upload(organization_id, project_id, request)

    async def sign_multipart_part(
        self,
        organization_id: UUID,
        upload_id: UUID,
        part_number: int,
    ) -> MultipartPartResponse:
        return await self.delegate.sign_multipart_part(
            organization_id,
            upload_id,
            part_number,
        )

    async def complete_upload(
        self,
        organization_id: UUID,
        upload_id: UUID,
        request: CompleteAssetUploadRequest,
    ) -> AssetResponse:
        asset = await self.delegate.complete_upload(organization_id, upload_id, request)
        await self.scheduler.schedule(
            JobScheduleRequest(
                job_id=new_uuid7(),
                organization_id=organization_id,
                project_id=asset.project_id,
                job_kind="asset.validate",
                resource_id=upload_id,
            )
        )
        return asset

    async def get_asset(self, organization_id: UUID, asset_id: UUID) -> AssetResponse:
        return await self.delegate.get_asset(organization_id, asset_id)

    async def get_download(
        self,
        organization_id: UUID,
        asset_id: UUID,
    ) -> AssetDownloadResponse:
        return await self.delegate.get_download(organization_id, asset_id)

    async def list_previews(
        self,
        organization_id: UUID,
        asset_id: UUID,
    ) -> AssetPreviewListResponse:
        return await self.delegate.list_previews(organization_id, asset_id)
