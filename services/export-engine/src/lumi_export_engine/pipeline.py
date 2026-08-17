from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from .model import (
    DownloadGrant,
    DownloadPackage,
    ExportFormat,
    ExportItemRuntime,
    ExportJob,
    ExportJobStatus,
    ExportTaskSpec,
    ExportedFile,
)
from .packaging import build_deterministic_zip, build_manifest
from .ports import (
    ArtifactSnapshotPort,
    DownloadGrantPort,
    ExportAuthorizationPort,
    ExportObjectStorePort,
    ExportQueuePort,
    ExportRendererPort,
    ExportRepositoryPort,
    ObjectReadPort,
)


class ExportOperationConflict(RuntimeError):
    pass


class ExportEngine:
    def __init__(
        self,
        *,
        snapshots: ArtifactSnapshotPort,
        authorization: ExportAuthorizationPort,
        repository: ExportRepositoryPort,
        queue: ExportQueuePort,
        reader: ObjectReadPort,
        renderers: tuple[ExportRendererPort, ...],
        store: ExportObjectStorePort,
        grants: DownloadGrantPort,
    ) -> None:
        self.snapshots = snapshots
        self.authorization = authorization
        self.repository = repository
        self.queue = queue
        self.reader = reader
        self.renderers = renderers
        self.store = store
        self.grants = grants

    def create(self, spec: ExportTaskSpec) -> ExportJob:
        runtimes: list[ExportItemRuntime] = []
        for request in spec.items:
            snapshot = self.snapshots.snapshot_exact(
                organization_id=spec.organization_id,
                project_id=spec.project_id,
                artifact_version_id=request.artifact_version_id,
            )
            if snapshot.artifact_version_id != request.artifact_version_id:
                raise ValueError("EXPORT_EXACT_VERSION_MISMATCH")
            self.authorization.authorize_snapshot(
                actor_id=spec.requested_by,
                snapshot=snapshot,
            )
            runtimes.append(ExportItemRuntime(request=request, snapshot=snapshot))
        job = ExportJob(
            job_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"lumi:export:{spec.organization_id}:{spec.operation_id}",
                )
            ),
            spec=spec,
            status=ExportJobStatus.PLANNED,
            items=tuple(runtimes),
        )
        persisted = self.repository.create(job)
        if persisted.spec.semantic_hash() != spec.semantic_hash():
            raise ExportOperationConflict("EXPORT_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC")
        if persisted.status is not ExportJobStatus.PLANNED:
            return persisted
        runtime_job_id = self.queue.enqueue(job=persisted)
        queued = replace(
            persisted,
            status=ExportJobStatus.QUEUED,
            runtime_job_id=runtime_job_id,
        )
        return self.repository.save(queued)

    async def execute(self, job_id: str) -> ExportJob:
        job = self.repository.get(job_id)
        if job.status in {ExportJobStatus.READY, ExportJobStatus.CANCELLED, ExportJobStatus.EXPIRED}:
            return job
        if job.status is ExportJobStatus.FAILED:
            return job
        if job.status not in {ExportJobStatus.QUEUED, ExportJobStatus.RENDERING, ExportJobStatus.PACKAGING}:
            return self.repository.save(
                replace(job, status=ExportJobStatus.FAILED, error_code="EXPORT_JOB_NOT_EXECUTABLE")
            )
        rendering = self.repository.save(
            replace(job, status=ExportJobStatus.RENDERING, error_code=None)
        )
        outputs: list[ExportedFile] = []
        payloads: list[bytes] = []
        total_bytes = 0
        try:
            for runtime in rendering.items:
                payload, mime_type, renderer_version = await self._render(runtime)
                total_bytes += len(payload)
                if total_bytes > rendering.spec.max_total_bytes:
                    raise ValueError("EXPORT_TOTAL_BYTES_EXCEEDED")
                checksum = hashlib.sha256(payload).hexdigest()
                bucket, storage_key = await self.store.put(
                    organization_id=rendering.spec.organization_id,
                    project_id=rendering.spec.project_id,
                    filename=runtime.request.output_name,
                    mime_type=mime_type,
                    payload=payload,
                    checksum_sha256=checksum,
                )
                output = ExportedFile(
                    name=runtime.request.output_name,
                    mime_type=mime_type,
                    bucket=bucket,
                    storage_key=storage_key,
                    size_bytes=len(payload),
                    checksum_sha256=checksum,
                    renderer_version=renderer_version,
                    source_artifact_id=runtime.snapshot.artifact_id,
                    source_artifact_version_id=runtime.snapshot.artifact_version_id,
                    source_file_ids=tuple(item.file_id for item in runtime.snapshot.files),
                )
                outputs.append(output)
                payloads.append(payload)
        except Exception as exc:
            return self.repository.save(
                replace(
                    rendering,
                    status=ExportJobStatus.FAILED,
                    outputs=tuple(outputs),
                    error_code=f"EXPORT_RENDER_FAILED:{type(exc).__name__}",
                )
            )

        packaging = self.repository.save(
            replace(rendering, status=ExportJobStatus.PACKAGING, outputs=tuple(outputs))
        )
        manifest = build_manifest(packaging, tuple(outputs))
        try:
            if len(outputs) == 1 and not packaging.spec.force_zip:
                output = outputs[0]
                package = DownloadPackage(
                    package_id=str(uuid5(NAMESPACE_URL, f"lumi:export-package:{packaging.job_id}")),
                    bucket=output.bucket,
                    storage_key=output.storage_key,
                    filename=output.name,
                    mime_type=output.mime_type,
                    size_bytes=output.size_bytes,
                    checksum_sha256=output.checksum_sha256,
                    manifest=manifest,
                    is_archive=False,
                )
            else:
                archive = build_deterministic_zip(
                    manifest=manifest,
                    files=tuple(zip(outputs, payloads, strict=True)),
                    max_total_bytes=packaging.spec.max_total_bytes,
                )
                checksum = hashlib.sha256(archive).hexdigest()
                filename = f"{packaging.spec.package_name}.zip"
                bucket, storage_key = await self.store.put(
                    organization_id=packaging.spec.organization_id,
                    project_id=packaging.spec.project_id,
                    filename=filename,
                    mime_type="application/zip",
                    payload=archive,
                    checksum_sha256=checksum,
                )
                package = DownloadPackage(
                    package_id=str(uuid5(NAMESPACE_URL, f"lumi:export-package:{packaging.job_id}")),
                    bucket=bucket,
                    storage_key=storage_key,
                    filename=filename,
                    mime_type="application/zip",
                    size_bytes=len(archive),
                    checksum_sha256=checksum,
                    manifest=manifest,
                    is_archive=True,
                )
        except Exception as exc:
            return self.repository.save(
                replace(
                    packaging,
                    status=ExportJobStatus.FAILED,
                    error_code=f"EXPORT_PACKAGING_FAILED:{type(exc).__name__}",
                )
            )
        return self.repository.save(
            replace(
                packaging,
                status=ExportJobStatus.READY,
                package=package,
                error_code=None,
            )
        )

    async def issue_download(self, job_id: str, *, actor_id: str) -> DownloadGrant:
        job = self.repository.get(job_id)
        if job.status is not ExportJobStatus.READY or job.package is None:
            raise ValueError("EXPORT_PACKAGE_NOT_READY")
        self.authorization.authorize_download(actor_id=actor_id, job=job)
        grant = await self.grants.issue(
            job=job,
            actor_id=actor_id,
            package=job.package,
            ttl_seconds=job.spec.download_ttl_seconds,
        )
        if grant.package_id != job.package.package_id or grant.actor_id != actor_id:
            raise ValueError("EXPORT_DOWNLOAD_GRANT_IDENTITY_MISMATCH")
        self.repository.record_grant(grant)
        return grant

    def cancel(self, job_id: str) -> ExportJob:
        job = self.repository.get(job_id)
        if job.status in {
            ExportJobStatus.READY,
            ExportJobStatus.FAILED,
            ExportJobStatus.CANCELLED,
            ExportJobStatus.EXPIRED,
        }:
            return job
        if job.runtime_job_id:
            self.queue.cancel(runtime_job_id=job.runtime_job_id)
        return self.repository.save(replace(job, status=ExportJobStatus.CANCELLED))

    async def _render(self, runtime: ExportItemRuntime) -> tuple[bytes, str, str]:
        if runtime.request.target_format is ExportFormat.ORIGINAL:
            source = runtime.snapshot.primary_file()
            payload = await self.reader.read_exact(source=source)
            if len(payload) != source.size_bytes:
                raise ValueError("EXPORT_SOURCE_SIZE_MISMATCH")
            if hashlib.sha256(payload).hexdigest() != source.checksum_sha256:
                raise ValueError("EXPORT_SOURCE_CHECKSUM_MISMATCH")
            return payload, source.mime_type, "copy-through/1.0"
        for renderer in self.renderers:
            if renderer.supports(
                artifact_type=runtime.snapshot.artifact_type,
                target_format=runtime.request.target_format,
            ):
                return await renderer.render(
                    snapshot=runtime.snapshot,
                    target_format=runtime.request.target_format,
                    output_name=runtime.request.output_name,
                )
        raise ValueError("EXPORT_FORMAT_NOT_SUPPORTED")
