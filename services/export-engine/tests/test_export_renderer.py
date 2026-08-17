from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest

from lumi_export_engine.model import (
    ArtifactVersionSnapshot,
    ExportFormat,
    ExportSourceFile,
)
from lumi_export_engine.renderers import VerifiedSameFormatRenderer


class Reader:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def read_exact(self, *, source):
        return self.payload


def snapshot(mime_type: str, payload: bytes) -> ArtifactVersionSnapshot:
    checksum = hashlib.sha256(payload).hexdigest()
    return ArtifactVersionSnapshot(
        organization_id="org",
        project_id="project",
        artifact_id="artifact",
        artifact_version_id="version",
        artifact_type="IMAGE",
        version_number=1,
        status="APPROVED",
        content_hash=checksum,
        primary_file_id="file-1",
        files=(
            ExportSourceFile(
                file_id="file-1",
                role="original",
                bucket="artifact-bucket",
                storage_key="objects/file.bin",
                mime_type=mime_type,
                size_bytes=len(payload),
                checksum_sha256=checksum,
            ),
        ),
        rights_review_status="UNREVIEWED",
        captured_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_same_format_png_returns_verified_exact_bytes():
    async def scenario():
        payload = b"real-png-bytes-for-contract"
        renderer = VerifiedSameFormatRenderer(Reader(payload))
        rendered, mime, version = await renderer.render(
            snapshot=snapshot("image/png", payload),
            target_format=ExportFormat.PNG,
            output_name="design.png",
        )
        assert rendered == payload
        assert mime == "image/png"
        assert version == "same-format/1.0"

    asyncio.run(scenario())


def test_mime_conversion_requires_real_transcoder():
    async def scenario():
        payload = b"jpeg"
        renderer = VerifiedSameFormatRenderer(Reader(payload))
        with pytest.raises(ValueError, match="TRANSCODER_REQUIRED"):
            await renderer.render(
                snapshot=snapshot("image/jpeg", payload),
                target_format=ExportFormat.PNG,
                output_name="design.png",
            )

    asyncio.run(scenario())
