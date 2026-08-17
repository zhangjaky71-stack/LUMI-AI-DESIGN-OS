from __future__ import annotations

from typing import Protocol

from .model import (
    ArtifactVersionSnapshot,
    DownloadGrant,
    DownloadPackage,
    ExportFormat,
    ExportJob,
    ExportSourceFile,
    ExportTaskSpec,
    ExportedFile,
)


class ArtifactSnapshotPort(Protocol):
    def snapshot_exact(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> ArtifactVersionSnapshot: ...


class ExportAuthorizationPort(Protocol):
    def authorize_snapshot(
        self,
        *,
        actor_id: str,
        snapshot: ArtifactVersionSnapshot,
    ) -> None: ...

    def authorize_download(
        self,
        *,
        actor_id: str,
        job: ExportJob,
    ) -> None: ...


class ObjectReadPort(Protocol):
    async def read_exact(self, *, source: ExportSourceFile) -> bytes: ...


class ExportRendererPort(Protocol):
    def supports(
        self,
        *,
        artifact_type: str,
        target_format: ExportFormat,
    ) -> bool: ...

    async def render(
        self,
        *,
        snapshot: ArtifactVersionSnapshot,
        target_format: ExportFormat,
        output_name: str,
    ) -> tuple[bytes, str, str]:
        """Return payload, MIME type, renderer version."""
        ...


class ExportObjectStorePort(Protocol):
    async def put(
        self,
        *,
        organization_id: str,
        project_id: str,
        filename: str,
        mime_type: str,
        payload: bytes,
        checksum_sha256: str,
    ) -> tuple[str, str]:
        """Return internal bucket and storage key."""
        ...


class DownloadGrantPort(Protocol):
    async def issue(
        self,
        *,
        job: ExportJob,
        actor_id: str,
        package: DownloadPackage,
        ttl_seconds: int,
    ) -> DownloadGrant: ...


class ExportRepositoryPort(Protocol):
    def create(self, job: ExportJob) -> ExportJob: ...

    def get(self, job_id: str) -> ExportJob: ...

    def save(self, job: ExportJob) -> ExportJob: ...

    def record_grant(self, grant: DownloadGrant) -> None: ...


class ExportQueuePort(Protocol):
    def enqueue(self, *, job: ExportJob) -> str: ...

    def cancel(self, *, runtime_job_id: str) -> bool: ...
