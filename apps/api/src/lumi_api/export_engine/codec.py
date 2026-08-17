from __future__ import annotations

from datetime import datetime
from typing import Any

from lumi_export_engine import (
    ArtifactVersionSnapshot,
    DownloadPackage,
    ExportFormat,
    ExportItemRuntime,
    ExportJob,
    ExportJobStatus,
    ExportManifest,
    ExportRequestItem,
    ExportSourceFile,
    ExportTaskSpec,
    ExportedFile,
    ManifestEntry,
)


def encode_job(job: ExportJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "spec": {
            "organization_id": job.spec.organization_id,
            "project_id": job.spec.project_id,
            "task_id": job.spec.task_id,
            "operation_id": job.spec.operation_id,
            "requested_by": job.spec.requested_by,
            "download_ttl_seconds": job.spec.download_ttl_seconds,
            "force_zip": job.spec.force_zip,
            "package_name": job.spec.package_name,
            "max_total_bytes": job.spec.max_total_bytes,
            "items": [
                {
                    "artifact_version_id": item.artifact_version_id,
                    "target_format": item.target_format.value,
                    "output_name": item.output_name,
                }
                for item in job.spec.items
            ],
        },
        "status": job.status.value,
        "runtime_job_id": job.runtime_job_id,
        "items": [
            {
                "request": {
                    "artifact_version_id": item.request.artifact_version_id,
                    "target_format": item.request.target_format.value,
                    "output_name": item.request.output_name,
                },
                "snapshot": encode_snapshot(item.snapshot),
            }
            for item in job.items
        ],
        "outputs": [encode_output(item) for item in job.outputs],
        "package": None if job.package is None else encode_package(job.package),
        "error_code": job.error_code,
    }


def encode_snapshot(value: ArtifactVersionSnapshot) -> dict[str, Any]:
    return {
        "organization_id": value.organization_id,
        "project_id": value.project_id,
        "artifact_id": value.artifact_id,
        "artifact_version_id": value.artifact_version_id,
        "artifact_type": value.artifact_type,
        "version_number": value.version_number,
        "status": value.status,
        "content_hash": value.content_hash,
        "primary_file_id": value.primary_file_id,
        "rights_review_status": value.rights_review_status,
        "captured_at": value.captured_at.isoformat(),
        "files": [
            {
                "file_id": item.file_id,
                "role": item.role,
                "bucket": item.bucket,
                "storage_key": item.storage_key,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "checksum_sha256": item.checksum_sha256,
            }
            for item in value.files
        ],
    }


def encode_output(value: ExportedFile) -> dict[str, Any]:
    return {
        "name": value.name,
        "mime_type": value.mime_type,
        "bucket": value.bucket,
        "storage_key": value.storage_key,
        "size_bytes": value.size_bytes,
        "checksum_sha256": value.checksum_sha256,
        "renderer_version": value.renderer_version,
        "source_artifact_id": value.source_artifact_id,
        "source_artifact_version_id": value.source_artifact_version_id,
        "source_file_ids": list(value.source_file_ids),
    }


def encode_manifest(value: ExportManifest) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "organization_id": value.organization_id,
        "project_id": value.project_id,
        "export_job_id": value.export_job_id,
        "operation_id": value.operation_id,
        "created_at": value.created_at.isoformat(),
        "exporter_version": value.exporter_version,
        "entries": [
            {
                "name": item.name,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "checksum_sha256": item.checksum_sha256,
                "artifact_id": item.artifact_id,
                "artifact_version_id": item.artifact_version_id,
                "source_file_ids": list(item.source_file_ids),
                "renderer_version": item.renderer_version,
            }
            for item in value.entries
        ],
    }


def encode_package(value: DownloadPackage) -> dict[str, Any]:
    return {
        "package_id": value.package_id,
        "bucket": value.bucket,
        "storage_key": value.storage_key,
        "filename": value.filename,
        "mime_type": value.mime_type,
        "size_bytes": value.size_bytes,
        "checksum_sha256": value.checksum_sha256,
        "manifest": encode_manifest(value.manifest),
        "is_archive": value.is_archive,
    }


def decode_job(value: dict[str, Any]) -> ExportJob:
    spec_value = value["spec"]
    spec = ExportTaskSpec(
        organization_id=str(spec_value["organization_id"]),
        project_id=str(spec_value["project_id"]),
        task_id=str(spec_value["task_id"]),
        operation_id=str(spec_value["operation_id"]),
        requested_by=str(spec_value["requested_by"]),
        items=tuple(
            ExportRequestItem(
                artifact_version_id=str(item["artifact_version_id"]),
                target_format=ExportFormat(str(item["target_format"])),
                output_name=str(item["output_name"]),
            )
            for item in spec_value["items"]
        ),
        download_ttl_seconds=int(spec_value["download_ttl_seconds"]),
        force_zip=bool(spec_value["force_zip"]),
        package_name=str(spec_value["package_name"]),
        max_total_bytes=int(spec_value["max_total_bytes"]),
    )
    return ExportJob(
        job_id=str(value["job_id"]),
        spec=spec,
        status=ExportJobStatus(str(value["status"])),
        items=tuple(
            ExportItemRuntime(
                request=ExportRequestItem(
                    artifact_version_id=str(item["request"]["artifact_version_id"]),
                    target_format=ExportFormat(str(item["request"]["target_format"])),
                    output_name=str(item["request"]["output_name"]),
                ),
                snapshot=decode_snapshot(item["snapshot"]),
            )
            for item in value["items"]
        ),
        runtime_job_id=value.get("runtime_job_id"),
        outputs=tuple(decode_output(item) for item in value.get("outputs", [])),
        package=(None if value.get("package") is None else decode_package(value["package"])),
        error_code=value.get("error_code"),
    )


def decode_snapshot(value: dict[str, Any]) -> ArtifactVersionSnapshot:
    return ArtifactVersionSnapshot(
        organization_id=str(value["organization_id"]),
        project_id=str(value["project_id"]),
        artifact_id=str(value["artifact_id"]),
        artifact_version_id=str(value["artifact_version_id"]),
        artifact_type=str(value["artifact_type"]),
        version_number=int(value["version_number"]),
        status=str(value["status"]),
        content_hash=str(value["content_hash"]),
        primary_file_id=value.get("primary_file_id"),
        files=tuple(
            ExportSourceFile(
                file_id=str(item["file_id"]),
                role=str(item["role"]),
                bucket=str(item["bucket"]),
                storage_key=str(item["storage_key"]),
                mime_type=str(item["mime_type"]),
                size_bytes=int(item["size_bytes"]),
                checksum_sha256=str(item["checksum_sha256"]),
            )
            for item in value["files"]
        ),
        rights_review_status=str(value["rights_review_status"]),
        captured_at=datetime.fromisoformat(str(value["captured_at"])),
    )


def decode_output(value: dict[str, Any]) -> ExportedFile:
    return ExportedFile(
        name=str(value["name"]),
        mime_type=str(value["mime_type"]),
        bucket=str(value["bucket"]),
        storage_key=str(value["storage_key"]),
        size_bytes=int(value["size_bytes"]),
        checksum_sha256=str(value["checksum_sha256"]),
        renderer_version=str(value["renderer_version"]),
        source_artifact_id=str(value["source_artifact_id"]),
        source_artifact_version_id=str(value["source_artifact_version_id"]),
        source_file_ids=tuple(str(item) for item in value.get("source_file_ids", [])),
    )


def decode_package(value: dict[str, Any]) -> DownloadPackage:
    manifest_value = value["manifest"]
    manifest = ExportManifest(
        schema_version=str(manifest_value["schema_version"]),
        organization_id=str(manifest_value["organization_id"]),
        project_id=str(manifest_value["project_id"]),
        export_job_id=str(manifest_value["export_job_id"]),
        operation_id=str(manifest_value["operation_id"]),
        created_at=datetime.fromisoformat(str(manifest_value["created_at"])),
        exporter_version=str(manifest_value["exporter_version"]),
        entries=tuple(
            ManifestEntry(
                name=str(item["name"]),
                mime_type=str(item["mime_type"]),
                size_bytes=int(item["size_bytes"]),
                checksum_sha256=str(item["checksum_sha256"]),
                artifact_id=str(item["artifact_id"]),
                artifact_version_id=str(item["artifact_version_id"]),
                source_file_ids=tuple(str(x) for x in item.get("source_file_ids", [])),
                renderer_version=str(item["renderer_version"]),
            )
            for item in manifest_value["entries"]
        ),
    )
    return DownloadPackage(
        package_id=str(value["package_id"]),
        bucket=str(value["bucket"]),
        storage_key=str(value["storage_key"]),
        filename=str(value["filename"]),
        mime_type=str(value["mime_type"]),
        size_bytes=int(value["size_bytes"]),
        checksum_sha256=str(value["checksum_sha256"]),
        manifest=manifest,
        is_archive=bool(value["is_archive"]),
    )
