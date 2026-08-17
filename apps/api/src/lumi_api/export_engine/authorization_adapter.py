from __future__ import annotations

from typing import Protocol

from lumi_export_engine import ArtifactVersionSnapshot, ExportJob


class ProjectAccessBackend(Protocol):
    def require_artifact_export(
        self,
        *,
        actor_id: str,
        organization_id: str,
        project_id: str,
        artifact_id: str,
        artifact_version_id: str,
    ) -> None: ...

    def require_package_download(
        self,
        *,
        actor_id: str,
        organization_id: str,
        project_id: str,
        export_job_id: str,
    ) -> None: ...


class Node11ExportAuthorizationAdapter:
    def __init__(self, backend: ProjectAccessBackend) -> None:
        self.backend = backend

    def authorize_snapshot(
        self,
        *,
        actor_id: str,
        snapshot: ArtifactVersionSnapshot,
    ) -> None:
        self.backend.require_artifact_export(
            actor_id=actor_id,
            organization_id=snapshot.organization_id,
            project_id=snapshot.project_id,
            artifact_id=snapshot.artifact_id,
            artifact_version_id=snapshot.artifact_version_id,
        )

    def authorize_download(self, *, actor_id: str, job: ExportJob) -> None:
        self.backend.require_package_download(
            actor_id=actor_id,
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            export_job_id=job.job_id,
        )
