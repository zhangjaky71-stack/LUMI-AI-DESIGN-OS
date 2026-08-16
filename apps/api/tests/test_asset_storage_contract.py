from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from lumi_api.assets import (
    AssetFileRole,
    AssetStatus,
    AssetStorageError,
    AssetStorageService,
    CompleteUploadCommand,
    CreateUploadCommand,
    DeterministicPreviewRenderer,
    FileScanResult,
    MemoryAssetRepository,
    MemoryObjectStore,
    QuotaPolicy,
    RightsAssertion,
    ScanStatus,
    UploadIntent,
    UploadStatus,
)
from lumi_api.auth import Permission, Principal

NOW = datetime(2026, 8, 16, 8, 15, tzinfo=UTC)
ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
USER_A = UUID("01910000-0000-7000-8000-000000000011")
PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00"
    b"fixture-payload"
)


class CleanScanner:
    def scan(self, path: Path) -> FileScanResult:
        assert path.exists()
        return FileScanResult(status=ScanStatus.CLEAN, engine="test-clean")


def principal(org: UUID = ORG_A) -> Principal:
    return Principal(
        actor_type="USER",
        actor_id=str(USER_A),
        user_id=USER_A,
        organization_id=org,
        roles=("editor",),
        permissions=(Permission.PROJECT_READ.value, Permission.ASSET_UPLOAD.value),
    )


def service(
    *,
    scanner: object | None = None,
    preview: bool = True,
    quota: QuotaPolicy | None = None,
) -> tuple[AssetStorageService, MemoryAssetRepository, MemoryObjectStore]:
    repo = MemoryAssetRepository(projects={(ORG_A, PROJECT_A)})
    store = MemoryObjectStore()
    svc = AssetStorageService(
        repo,
        store,
        scanner=scanner or CleanScanner(),
        preview_renderer=DeterministicPreviewRenderer() if preview else None,
        quota=quota or QuotaPolicy(require_scanner=True),
    )
    return svc, repo, store


def create_png_upload(
    svc: AssetStorageService,
    *,
    filename: str = "input.png",
    expected_checksum: str | None = None,
):
    checksum = expected_checksum or hashlib.sha256(PNG).hexdigest()
    return svc.create_upload(
        CreateUploadCommand(
            organization_id=ORG_A,
            project_id=PROJECT_A,
            filename=filename,
            declared_mime_type="image/png",
            expected_size=len(PNG),
            expected_checksum_sha256=checksum,
            rights_assertion=RightsAssertion.USER_OWNED,
            actor=principal(),
            now=NOW,
        )
    )


def memory_intent(grant) -> UploadIntent:
    return UploadIntent(
        bucket=grant.upload.bucket,
        key=grant.upload.object_key,
        expected_checksum_sha256=grant.upload.expected_checksum_sha256,
        declared_mime_type=grant.upload.declared_mime_type,
        expires_seconds=900,
    )


def test_direct_upload_complete_validate_and_preview_pipeline() -> None:
    svc, repo, store = service()
    grant = create_png_upload(svc)
    assert grant.request is not None
    assert grant.request.method == "PUT"
    assert grant.asset.status is AssetStatus.UPLOADING
    assert grant.upload.object_key == (
        f"org/{ORG_A}/project/{PROJECT_A}/asset/{grant.asset.id}/"
        f"original/{grant.upload.file_id}"
    )

    store.set_uploaded_bytes(memory_intent(grant), PNG)
    verifying = svc.complete_upload(
        CompleteUploadCommand(
            organization_id=ORG_A,
            upload_id=grant.upload.id,
            actor=principal(),
            now=NOW + timedelta(seconds=1),
        )
    )
    assert verifying.status is AssetStatus.VERIFYING

    report = svc.validate_upload(
        ORG_A,
        grant.upload.id,
        now=NOW + timedelta(seconds=2),
    )
    assert report.accepted is True
    asset = repo.get_asset(ORG_A, grant.asset.id)
    assert asset is not None and asset.status is AssetStatus.READY
    assert asset.mime_type == "image/png"
    assert len(repo.list_previews(ORG_A, asset.id)) == 2
    roles = {file.role for file in repo.list_files(ORG_A, asset.id)}
    assert {AssetFileRole.ORIGINAL, AssetFileRole.THUMBNAIL, AssetFileRole.MEDIUM} <= roles


def test_wrong_checksum_is_rejected_before_worker_validation() -> None:
    svc, _, store = service()
    grant = create_png_upload(svc)
    corrupted = b"x" * len(PNG)
    store.set_uploaded_bytes(memory_intent(grant), corrupted)
    with pytest.raises(AssetStorageError, match="UPLOADED_OBJECT_CHECKSUM_MISMATCH"):
        svc.complete_upload(
            CompleteUploadCommand(
                organization_id=ORG_A,
                upload_id=grant.upload.id,
                actor=principal(),
                now=NOW + timedelta(seconds=1),
            )
        )


def test_file_size_quota_is_checked_before_signing() -> None:
    svc, _, _ = service(
        quota=QuotaPolicy(
            max_file_bytes=10,
            max_org_storage_bytes=100,
            multipart_threshold_bytes=5 * 1024 * 1024,
            require_scanner=True,
        )
    )
    with pytest.raises(AssetStorageError, match="UPLOAD_FILE_SIZE_LIMIT_EXCEEDED"):
        create_png_upload(svc)


def test_fake_filename_extension_does_not_control_verified_mime() -> None:
    svc, repo, store = service()
    grant = create_png_upload(svc, filename="totally-not-a-png.exe.jpg")
    store.set_uploaded_bytes(memory_intent(grant), PNG)
    svc.complete_upload(
        CompleteUploadCommand(
            organization_id=ORG_A,
            upload_id=grant.upload.id,
            actor=principal(),
            now=NOW + timedelta(seconds=1),
        )
    )
    report = svc.validate_upload(ORG_A, grant.upload.id, now=NOW + timedelta(seconds=2))
    assert report.sniffed_mime_type == "image/png"
    asset = repo.get_asset(ORG_A, grant.asset.id)
    assert asset is not None and asset.mime_type == "image/png"


def test_malicious_svg_is_rejected_and_candidate_deleted() -> None:
    svc, repo, store = service(preview=False)
    payload = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    checksum = hashlib.sha256(payload).hexdigest()
    grant = svc.create_upload(
        CreateUploadCommand(
            organization_id=ORG_A,
            project_id=PROJECT_A,
            filename="unsafe.svg",
            declared_mime_type="image/svg+xml",
            expected_size=len(payload),
            expected_checksum_sha256=checksum,
            rights_assertion=RightsAssertion.UNKNOWN,
            actor=principal(),
            now=NOW,
        )
    )
    store.set_uploaded_bytes(memory_intent(grant), payload)
    svc.complete_upload(
        CompleteUploadCommand(
            organization_id=ORG_A,
            upload_id=grant.upload.id,
            actor=principal(),
            now=NOW + timedelta(seconds=1),
        )
    )
    report = svc.validate_upload(ORG_A, grant.upload.id, now=NOW + timedelta(seconds=2))
    assert report.accepted is False
    assert "SVG_ACTIVE_CONTENT_REJECTED" in report.reason_codes
    asset = repo.get_asset(ORG_A, grant.asset.id)
    assert asset is not None and asset.status is AssetStatus.REJECTED
    assert store.head(grant.upload.bucket, grant.upload.object_key, now=NOW).exists is False


def test_scanner_unavailable_fails_closed_when_required() -> None:
    from lumi_api.assets import UnavailableFileScanner

    svc, repo, store = service(scanner=UnavailableFileScanner(), preview=False)
    grant = create_png_upload(svc)
    store.set_uploaded_bytes(memory_intent(grant), PNG)
    svc.complete_upload(
        CompleteUploadCommand(
            organization_id=ORG_A,
            upload_id=grant.upload.id,
            actor=principal(),
            now=NOW + timedelta(seconds=1),
        )
    )
    report = svc.validate_upload(ORG_A, grant.upload.id, now=NOW + timedelta(seconds=2))
    assert report.accepted is False
    assert report.scan.status is ScanStatus.UNAVAILABLE
    assert repo.get_asset(ORG_A, grant.asset.id).status is AssetStatus.REJECTED  # type: ignore[union-attr]


def test_cross_tenant_read_and_download_are_indistinguishable_from_missing() -> None:
    svc, _, _ = service()
    grant = create_png_upload(svc)
    with pytest.raises(AssetStorageError, match="TENANT_RESOURCE_NOT_FOUND"):
        svc.get_asset(ORG_B, grant.asset.id, actor=principal(ORG_B))
    with pytest.raises(AssetStorageError, match="TENANT_RESOURCE_NOT_FOUND"):
        svc.signed_download(
            ORG_B,
            grant.asset.id,
            actor=principal(ORG_B),
            now=NOW,
        )


def test_download_is_short_lived_and_only_after_ready() -> None:
    svc, _, store = service()
    grant = create_png_upload(svc)
    with pytest.raises(AssetStorageError, match="ASSET_NOT_READY"):
        svc.signed_download(ORG_A, grant.asset.id, actor=principal(), now=NOW)
    store.set_uploaded_bytes(memory_intent(grant), PNG)
    svc.complete_upload(
        CompleteUploadCommand(
            organization_id=ORG_A,
            upload_id=grant.upload.id,
            actor=principal(),
            now=NOW + timedelta(seconds=1),
        )
    )
    svc.validate_upload(ORG_A, grant.upload.id, now=NOW + timedelta(seconds=2))
    signed = svc.signed_download(
        ORG_A,
        grant.asset.id,
        actor=principal(),
        now=NOW + timedelta(seconds=3),
    )
    assert signed.expires_at <= NOW + timedelta(seconds=303)
    assert "lumi_minio_local_only" not in signed.url


def test_orphan_cleanup_marks_expired_and_deletes_candidate() -> None:
    svc, repo, store = service()
    grant = create_png_upload(svc)
    store.set_uploaded_bytes(memory_intent(grant), PNG)
    count = svc.cleanup_orphans(
        ORG_A,
        before=grant.upload.expires_at + timedelta(seconds=1),
        now=grant.upload.expires_at + timedelta(seconds=2),
    )
    assert count == 1
    upload = repo.get_upload(ORG_A, grant.upload.id)
    assert upload is not None and upload.status is UploadStatus.EXPIRED
    assert store.head(grant.upload.bucket, grant.upload.object_key, now=NOW).exists is False
