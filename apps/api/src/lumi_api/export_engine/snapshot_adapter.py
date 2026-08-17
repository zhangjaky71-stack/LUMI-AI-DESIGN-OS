from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_api.artifact_engine.ports import ArtifactRepository
from lumi_export_engine import ArtifactVersionSnapshot, ExportSourceFile


class Node42ArtifactSnapshotAdapter:
    """Reads one exact immutable ArtifactVersion; never resolves a branch head."""

    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def snapshot_exact(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> ArtifactVersionSnapshot:
        version = self.repository.get_version(UUID(artifact_version_id))
        if str(version.organization_id) != organization_id:
            raise PermissionError("EXPORT_ARTIFACT_ORGANIZATION_MISMATCH")
        artifact = self.repository.get_artifact(version.artifact_id)
        if str(artifact.organization_id) != organization_id:
            raise PermissionError("EXPORT_ARTIFACT_ORGANIZATION_MISMATCH")
        if str(artifact.project_id) != project_id:
            raise PermissionError("EXPORT_ARTIFACT_PROJECT_MISMATCH")
        if str(version.id) != artifact_version_id:
            raise ValueError("EXPORT_EXACT_VERSION_MISMATCH")
        return ArtifactVersionSnapshot(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=str(artifact.id),
            artifact_version_id=str(version.id),
            artifact_type=artifact.type.value,
            version_number=version.version_number,
            status=version.status.value,
            content_hash=version.content_hash,
            primary_file_id=(
                str(version.primary_file_id)
                if version.primary_file_id is not None
                else None
            ),
            files=tuple(
                ExportSourceFile(
                    file_id=str(item.id),
                    role=item.role.value.lower(),
                    bucket=item.bucket,
                    storage_key=item.storage_key,
                    mime_type=item.mime_type,
                    size_bytes=item.size_bytes,
                    checksum_sha256=item.checksum_sha256,
                )
                for item in version.files
            ),
            rights_review_status=version.rights.review_status.value,
            captured_at=datetime.now(UTC),
        )
