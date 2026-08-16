from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from lumi_api.assets import (
    AssetStorageService,
    CompleteUploadCommand,
    CreateUploadCommand,
    FileScanResult,
    MemoryAssetRepository,
    MemoryObjectStore,
    QuotaPolicy,
    RightsAssertion,
    ScanStatus,
    UploadIntent,
    UploadMode,
)
from lumi_api.auth import Permission, Principal

NOW = datetime(2026, 8, 16, 8, 30, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
USER = UUID("01910000-0000-7000-8000-000000000011")


class CleanScanner:
    def scan(self, _path):
        return FileScanResult(status=ScanStatus.CLEAN, engine="test")


def principal() -> Principal:
    return Principal(
        actor_type="USER",
        actor_id=str(USER),
        user_id=USER,
        organization_id=ORG,
        permissions=(Permission.PROJECT_READ.value, Permission.ASSET_UPLOAD.value),
    )


def test_multipart_sign_complete_and_validate() -> None:
    part1 = b"\x89PNG\r\n\x1a\n" + b"a" * 64
    part2 = b"b" * 64
    payload = part1 + part2
    checksum = hashlib.sha256(payload).hexdigest()
    repository = MemoryAssetRepository(projects={(ORG, PROJECT)})
    object_store = MemoryObjectStore()
    service = AssetStorageService(
        repository,
        object_store,
        scanner=CleanScanner(),
        quota=QuotaPolicy(
            max_file_bytes=1024,
            max_org_storage_bytes=4096,
            multipart_threshold_bytes=5 * 1024 * 1024,
            require_scanner=True,
        ).model_copy(update={"multipart_threshold_bytes": 1}),
    )
    grant = service.create_upload(
        CreateUploadCommand(
            organization_id=ORG,
            project_id=PROJECT,
            filename="large.png",
            declared_mime_type="image/png",
            expected_size=len(payload),
            expected_checksum_sha256=checksum,
            rights_assertion=RightsAssertion.UNKNOWN,
            actor=principal(),
            now=NOW,
        )
    )
    assert grant.upload.mode is UploadMode.MULTIPART
    assert grant.multipart_upload_id is not None
    intent = UploadIntent(
        bucket=grant.upload.bucket,
        key=grant.upload.object_key,
        expected_checksum_sha256=checksum,
        declared_mime_type="image/png",
        expires_seconds=900,
    )
    signed1 = service.sign_multipart_part(
        ORG, grant.upload.id, part_number=1, actor=principal(), now=NOW
    )
    signed2 = service.sign_multipart_part(
        ORG, grant.upload.id, part_number=2, actor=principal(), now=NOW
    )
    assert "partNumber=1" in signed1.url
    assert "partNumber=2" in signed2.url
    object_store.set_part(grant.multipart_upload_id, 1, part1)
    object_store.set_part(grant.multipart_upload_id, 2, part2)
    service.complete_upload(
        CompleteUploadCommand(
            organization_id=ORG,
            upload_id=grant.upload.id,
            actor=principal(),
            now=NOW + timedelta(seconds=1),
            multipart_parts=((1, "etag-1"), (2, "etag-2")),
        )
    )
    report = service.validate_upload(
        ORG, grant.upload.id, now=NOW + timedelta(seconds=2)
    )
    assert report.accepted is True
    assert object_store.head(intent.bucket, intent.key, now=NOW).byte_size == len(payload)
