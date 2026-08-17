from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime

from .model import ExportJob, ExportManifest, ExportedFile, ManifestEntry


EXPORTER_VERSION = "export-engine/1.0.0"


def build_manifest(job: ExportJob, outputs: tuple[ExportedFile, ...]) -> ExportManifest:
    entries = tuple(
        ManifestEntry(
            name=item.name,
            mime_type=item.mime_type,
            size_bytes=item.size_bytes,
            checksum_sha256=item.checksum_sha256,
            artifact_id=item.source_artifact_id,
            artifact_version_id=item.source_artifact_version_id,
            source_file_ids=item.source_file_ids,
            renderer_version=item.renderer_version,
        )
        for item in outputs
    )
    return ExportManifest(
        schema_version="lumi.export-manifest/1.0",
        organization_id=job.spec.organization_id,
        project_id=job.spec.project_id,
        export_job_id=job.job_id,
        operation_id=job.spec.operation_id,
        created_at=datetime.now(UTC),
        exporter_version=EXPORTER_VERSION,
        entries=entries,
    )


def manifest_bytes(manifest: ExportManifest) -> bytes:
    payload = asdict(manifest)
    payload["created_at"] = manifest.created_at.isoformat()
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_deterministic_zip(
    *,
    manifest: ExportManifest,
    files: tuple[tuple[ExportedFile, bytes], ...],
    max_total_bytes: int,
) -> bytes:
    if not files or len(files) > 500:
        raise ValueError("EXPORT_ARCHIVE_ENTRY_COUNT_INVALID")
    total = sum(len(payload) for _, payload in files)
    if total > max_total_bytes:
        raise ValueError("EXPORT_TOTAL_BYTES_EXCEEDED")
    names = [item.name for item, _ in files]
    if len(names) != len(set(names)):
        raise ValueError("EXPORT_DUPLICATE_OUTPUT_NAME")
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for item, payload in sorted(files, key=lambda pair: pair[0].name):
            if hashlib.sha256(payload).hexdigest() != item.checksum_sha256:
                raise ValueError("EXPORT_OUTPUT_CHECKSUM_MISMATCH")
            info = zipfile.ZipInfo(item.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
        info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, manifest_bytes(manifest))
    payload = buffer.getvalue()
    if len(payload) > max_total_bytes:
        raise ValueError("EXPORT_ARCHIVE_BYTES_EXCEEDED")
    return payload
