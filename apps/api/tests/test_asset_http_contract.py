from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app
from lumi_api.api.v1.asset_dependencies import get_asset_api_service
from lumi_api.api.v1.auth_guard import _permission_for_request, enforce_api_auth
from lumi_api.assets.api import (
    AssetDownloadResponse,
    AssetPreviewListResponse,
    AssetResponse,
    CompleteAssetUploadRequest,
    CreateAssetUploadResponse,
    SignedRequestResponse,
)
from lumi_api.assets.models import AssetStatus, RightsAssertion
from lumi_api.auth import Permission

ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
ASSET = UUID("01910000-0000-7000-8000-000000000051")
UPLOAD = UUID("01910000-0000-7000-8000-000000000501")
NOW = datetime(2026, 8, 16, 8, 25, tzinfo=UTC)


class FakeAssetApiService:
    async def create_upload(self, organization_id, project_id, request):
        assert organization_id == ORG and project_id == PROJECT
        return CreateAssetUploadResponse(
            asset_id=ASSET,
            upload_id=UPLOAD,
            status=AssetStatus.UPLOADING,
            upload_mode="single_put",
            upload_request=SignedRequestResponse(
                method="PUT",
                url="https://storage.invalid/signed",
                expires_at=NOW + timedelta(minutes=5),
                headers={"x-amz-checksum-sha256": "fixture"},
            ),
            expires_at=NOW + timedelta(minutes=15),
        )

    async def sign_multipart_part(self, organization_id, upload_id, part_number):
        raise AssertionError("not used")

    async def complete_upload(
        self,
        organization_id: UUID,
        upload_id: UUID,
        request: CompleteAssetUploadRequest,
    ) -> AssetResponse:
        assert organization_id == ORG and upload_id == UPLOAD
        return AssetResponse(
            id=ASSET,
            organization_id=ORG,
            project_id=PROJECT,
            original_filename="input.png",
            declared_mime_type="image/png",
            status=AssetStatus.VERIFYING,
            rights_assertion=RightsAssertion.USER_OWNED,
            created_at=NOW,
            updated_at=NOW,
        )

    async def get_asset(self, organization_id: UUID, asset_id: UUID) -> AssetResponse:
        raise AssertionError("not used")

    async def get_download(self, organization_id, asset_id):
        return AssetDownloadResponse(
            asset_id=asset_id,
            request=SignedRequestResponse(
                method="GET",
                url="https://storage.invalid/download",
                expires_at=NOW + timedelta(minutes=5),
            ),
        )

    async def list_previews(self, organization_id, asset_id):
        return AssetPreviewListResponse(asset_id=asset_id, items=())


def _app():
    app = create_contract_app()
    app.dependency_overrides[enforce_api_auth] = lambda: None
    app.dependency_overrides[get_asset_api_service] = lambda: FakeAssetApiService()
    return app


def test_asset_routes_never_accept_binary_upload_body() -> None:
    schema = create_contract_app().openapi()
    paths = schema["paths"]
    expected = {
        "/api/v1/projects/{project_id}/assets/uploads",
        "/api/v1/assets/uploads/{upload_id}/parts/{part_number}",
        "/api/v1/assets/uploads/{upload_id}/complete",
        "/api/v1/assets/{asset_id}",
        "/api/v1/assets/{asset_id}/download",
        "/api/v1/assets/{asset_id}/previews",
    }
    assert expected <= set(paths)
    create_schema = paths["/api/v1/projects/{project_id}/assets/uploads"]["post"]
    content = create_schema["requestBody"]["content"]
    assert set(content) == {"application/json"}


def test_create_upload_returns_presigned_put_not_binary_proxy() -> None:
    client = TestClient(_app())
    response = client.post(
        f"/api/v1/projects/{PROJECT}/assets/uploads",
        headers={"X-Organization-ID": str(ORG)},
        json={
            "filename": "input.png",
            "content_type": "image/png",
            "byte_size": 123,
            "checksum_sha256": "a" * 64,
            "rights_assertion": "USER_OWNED",
        },
    )
    assert response.status_code == 201
    assert response.json()["upload_request"]["method"] == "PUT"
    assert "file" not in response.json()


def test_complete_upload_returns_202_verifying() -> None:
    client = TestClient(_app())
    response = client.post(
        f"/api/v1/assets/uploads/{UPLOAD}/complete",
        headers={"X-Organization-ID": str(ORG)},
        json={"parts": []},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "verifying"


def test_auth_guard_maps_asset_mutations_to_asset_upload_permission() -> None:
    from starlette.requests import Request

    create = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/projects/{PROJECT}/assets/uploads",
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    read = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/assets/{ASSET}/download",
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    assert _permission_for_request(create) is Permission.ASSET_UPLOAD
    assert _permission_for_request(read) is Permission.PROJECT_READ
