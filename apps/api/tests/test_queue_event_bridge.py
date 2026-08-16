from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from lumi_api.assets.api import (
    AssetDownloadResponse,
    AssetPreviewListResponse,
    AssetResponse,
    CompleteAssetUploadRequest,
    CreateAssetUploadRequest,
    CreateAssetUploadResponse,
    MultipartPartResponse,
)
from lumi_api.assets.models import (
    AssetEvent,
    AssetEventType,
    AssetRecord,
    AssetStatus,
    MediaKind,
    RightsAssertion,
)
from lumi_api.domain.ids import new_uuid7
from lumi_api.events.runtime_bridge import (
    asset_ready_envelope,
    outbox_row,
    project_created_envelope,
)
from lumi_api.projects.models import (
    ProjectBrief,
    ProjectEvent,
    ProjectEventType,
    ProjectRecord,
    ProjectSettings,
)
from lumi_api.domain.states import ProjectStatus
from lumi_api.queueing import MemoryJobScheduler, QueuedAssetApiService

NOW = datetime(2026, 8, 16, 8, 55, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")
ASSET = UUID("01910000-0000-7000-8000-000000000051")
UPLOAD = UUID("01910000-0000-7000-8000-000000000501")


def test_project_and_asset_events_bridge_to_node12_envelopes() -> None:
    project = ProjectRecord(
        id=PROJECT,
        organization_id=ORG,
        workspace_id=WORKSPACE,
        name="Bridge",
        status=ProjectStatus.DRAFT,
        brief=ProjectBrief(),
        settings=ProjectSettings(),
        version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    project_event = ProjectEvent(
        organization_id=ORG,
        project_id=PROJECT,
        event_type=ProjectEventType.CREATED,
        occurred_at=NOW,
    )
    project_envelope = project_created_envelope(project, project_event)
    assert project_envelope.event_id == project_event.id
    assert project_envelope.event_type == "lumi.project.created.v1"
    assert project_envelope.payload.project_version == 3
    assert outbox_row(project_envelope)["payload_json"]["spec_version"] == "lumi.events/1.0"

    asset = AssetRecord(
        id=ASSET,
        organization_id=ORG,
        project_id=PROJECT,
        original_filename="input.png",
        declared_mime_type="image/png",
        mime_type="image/png",
        media_kind=MediaKind.IMAGE,
        status=AssetStatus.READY,
        rights_assertion=RightsAssertion.UNKNOWN,
        created_at=NOW,
        updated_at=NOW,
    )
    asset_event = AssetEvent(
        organization_id=ORG,
        project_id=PROJECT,
        asset_id=ASSET,
        event_type=AssetEventType.READY,
        occurred_at=NOW,
    )
    asset_envelope = asset_ready_envelope(
        asset,
        asset_event,
        checksum_sha256="a" * 64,
    )
    assert asset_envelope.event_id == asset_event.id
    assert asset_envelope.event_type == "lumi.asset.ready.v1"
    assert asset_envelope.payload.checksum_sha256 == "a" * 64


class FakeAssetApi:
    async def create_upload(self, organization_id, project_id, request):
        return CreateAssetUploadResponse(
            asset_id=ASSET,
            upload_id=UPLOAD,
            status=AssetStatus.UPLOADING,
            upload_mode="single_put",
            expires_at=NOW,
        )

    async def sign_multipart_part(self, organization_id, upload_id, part_number):
        raise AssertionError("not used")

    async def complete_upload(self, organization_id, upload_id, request):
        return AssetResponse(
            id=ASSET,
            organization_id=ORG,
            project_id=PROJECT,
            original_filename="input.png",
            declared_mime_type="image/png",
            status=AssetStatus.VERIFYING,
            rights_assertion=RightsAssertion.UNKNOWN,
            created_at=NOW,
            updated_at=NOW,
        )

    async def get_asset(self, organization_id, asset_id):
        raise AssertionError("not used")

    async def get_download(self, organization_id, asset_id):
        raise AssertionError("not used")

    async def list_previews(self, organization_id, asset_id):
        return AssetPreviewListResponse(asset_id=asset_id, items=())


def test_asset_completion_schedules_validation_job_by_ids_only() -> None:
    scheduler = MemoryJobScheduler()
    service = QueuedAssetApiService(FakeAssetApi(), scheduler)
    asyncio.run(service.complete_upload(ORG, UPLOAD, CompleteAssetUploadRequest()))
    assert len(scheduler.requests) == 1
    request = scheduler.requests[0]
    assert request.job_id.version == 7
    assert request.job_kind == "asset.validate"
    assert request.resource_id == UPLOAD
    assert request.organization_id == ORG
    assert request.project_id == PROJECT
    serialized = request.model_dump(mode="json")
    assert not any("url" in key.casefold() for key in serialized)
