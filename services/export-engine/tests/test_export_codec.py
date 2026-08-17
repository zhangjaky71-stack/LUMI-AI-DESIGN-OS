from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from lumi_api.export_engine.codec import decode_job, encode_job
from lumi_export_engine import (
    ArtifactVersionSnapshot,
    ExportFormat,
    ExportItemRuntime,
    ExportJob,
    ExportJobStatus,
    ExportRequestItem,
    ExportSourceFile,
    ExportTaskSpec,
)


def test_queued_job_codec_round_trip_preserves_exact_snapshot():
    payload = b"approved-png"
    checksum = hashlib.sha256(payload).hexdigest()
    version_id = "33333333-3333-4333-8333-333333333333"
    request = ExportRequestItem(
        artifact_version_id=version_id,
        target_format=ExportFormat.PNG,
        output_name="hero.png",
    )
    spec = ExportTaskSpec(
        organization_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        task_id="44444444-4444-4444-8444-444444444444",
        operation_id="55555555-5555-4555-8555-555555555555",
        requested_by="user-1",
        items=(request,),
    )
    snapshot = ArtifactVersionSnapshot(
        organization_id=spec.organization_id,
        project_id=spec.project_id,
        artifact_id="66666666-6666-4666-8666-666666666666",
        artifact_version_id=version_id,
        artifact_type="IMAGE",
        version_number=9,
        status="APPROVED",
        content_hash=checksum,
        primary_file_id="77777777-7777-4777-8777-777777777777",
        files=(
            ExportSourceFile(
                file_id="77777777-7777-4777-8777-777777777777",
                role="original",
                bucket="artifact-bucket",
                storage_key="objects/hero.png",
                mime_type="image/png",
                size_bytes=len(payload),
                checksum_sha256=checksum,
            ),
        ),
        rights_review_status="UNREVIEWED",
        captured_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )
    job = ExportJob(
        job_id="88888888-8888-4888-8888-888888888888",
        spec=spec,
        status=ExportJobStatus.QUEUED,
        items=(ExportItemRuntime(request=request, snapshot=snapshot),),
        runtime_job_id="99999999-9999-4999-8999-999999999999",
    )

    decoded = decode_job(encode_job(job))

    assert decoded == job
    assert decoded.items[0].snapshot.artifact_version_id == version_id
    assert decoded.items[0].snapshot.version_number == 9
    assert decoded.spec.semantic_hash() == spec.semantic_hash()
