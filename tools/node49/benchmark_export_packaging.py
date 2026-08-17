from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime

from lumi_export_engine.model import (
    ExportFormat,
    ExportItemRuntime,
    ExportJob,
    ExportJobStatus,
    ExportRequestItem,
    ExportTaskSpec,
    ExportedFile,
    ArtifactVersionSnapshot,
    ExportSourceFile,
)
from lumi_export_engine.packaging import build_deterministic_zip, build_manifest


def main() -> None:
    payload = b"x" * 1024
    checksum = hashlib.sha256(payload).hexdigest()
    items = []
    outputs = []
    files = []
    for index in range(500):
        version_id = f"00000000-0000-4000-8000-{index:012d}"
        artifact_id = f"10000000-0000-4000-8000-{index:012d}"
        request = ExportRequestItem(
            artifact_version_id=version_id,
            target_format=ExportFormat.ORIGINAL,
            output_name=f"asset-{index:03d}.bin",
        )
        snapshot = ArtifactVersionSnapshot(
            organization_id="org",
            project_id="project",
            artifact_id=artifact_id,
            artifact_version_id=version_id,
            artifact_type="BINARY",
            version_number=1,
            status="APPROVED",
            content_hash=checksum,
            primary_file_id=f"file-{index}",
            files=(
                ExportSourceFile(
                    file_id=f"file-{index}",
                    role="original",
                    bucket="source",
                    storage_key=f"objects/{index}.bin",
                    mime_type="application/octet-stream",
                    size_bytes=len(payload),
                    checksum_sha256=checksum,
                ),
            ),
            rights_review_status="UNREVIEWED",
            captured_at=datetime(2026, 8, 17, tzinfo=UTC),
        )
        items.append(ExportItemRuntime(request=request, snapshot=snapshot))
        output = ExportedFile(
            name=request.output_name,
            mime_type="application/octet-stream",
            bucket="exports",
            storage_key=f"output/{index}.bin",
            size_bytes=len(payload),
            checksum_sha256=checksum,
            renderer_version="copy-through/1.0",
            source_artifact_id=artifact_id,
            source_artifact_version_id=version_id,
            source_file_ids=(f"file-{index}",),
        )
        outputs.append(output)
        files.append((output, payload))
    spec = ExportTaskSpec(
        organization_id="org",
        project_id="project",
        task_id="task",
        operation_id="benchmark",
        requested_by="benchmark",
        items=tuple(item.request for item in items),
        force_zip=True,
    )
    job = ExportJob(
        job_id="benchmark-job",
        spec=spec,
        status=ExportJobStatus.PACKAGING,
        items=tuple(items),
        outputs=tuple(outputs),
    )
    started = time.perf_counter()
    manifest = build_manifest(job, tuple(outputs))
    archive = build_deterministic_zip(
        manifest=manifest,
        files=tuple(files),
        max_total_bytes=spec.max_total_bytes,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert len(manifest.entries) == 500
    assert len(archive) > 0
    print(
        "NODE49_EXPORT_PACKAGING_BENCHMARK_PASS "
        f"entries=500 bytes={len(archive)} elapsed_ms={elapsed_ms:.3f}"
    )


if __name__ == "__main__":
    main()
