from __future__ import annotations

from uuid import UUID

from lumi_api.artifact_engine.ports import ArtifactRepository
from lumi_visual_critic.model import ArtifactQualityInput


class Node42QualityArtifactAdapter:
    """Loads one exact immutable ArtifactVersion; never resolves branch head/latest."""

    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def load_exact(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> ArtifactQualityInput:
        version = self.repository.get_version(UUID(artifact_version_id))
        artifact = self.repository.get_artifact(version.artifact_id)
        if str(version.id) != artifact_version_id:
            raise ValueError("QUALITY_EXACT_ARTIFACT_VERSION_MISMATCH")
        if str(version.organization_id) != organization_id:
            raise PermissionError("QUALITY_ARTIFACT_ORGANIZATION_MISMATCH")
        if str(artifact.organization_id) != organization_id:
            raise PermissionError("QUALITY_ARTIFACT_ORGANIZATION_MISMATCH")
        if str(artifact.project_id) != project_id:
            raise PermissionError("QUALITY_ARTIFACT_PROJECT_MISMATCH")
        primary = None
        if version.primary_file_id is not None:
            primary = next(
                (item for item in version.files if item.id == version.primary_file_id),
                None,
            )
        if primary is None and len(version.files) == 1:
            primary = version.files[0]
        if primary is None:
            raise ValueError("QUALITY_PRIMARY_FILE_REQUIRED")
        metadata = dict(primary.metadata)
        identity_refs = tuple(
            sorted(
                item.strip()
                for item in metadata.get("identity_refs", "").split(",")
                if item.strip()
            )
        )
        return ArtifactQualityInput(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=str(artifact.id),
            artifact_version_id=str(version.id),
            artifact_type=artifact.type.value,
            content_hash=version.content_hash,
            primary_file_ref=f"{primary.bucket}:{primary.storage_key}",
            metadata={
                **metadata,
                "mime_type": primary.mime_type,
                "size_bytes": primary.size_bytes,
                "width": primary.width,
                "height": primary.height,
                "duration_ms": primary.duration_ms,
                "constraint_snapshot_hash": version.constraint_snapshot_hash,
                "artifact_version_status": version.status.value,
            },
            design_ir_ref=(
                str(version.design_document_version_id)
                if version.design_document_version_id is not None
                else None
            ),
            brand_rule_snapshot_id=metadata.get("brand_rule_snapshot_id"),
            identity_refs=identity_refs,
            generation_provider=version.provenance.provider,
            generation_model=version.provenance.model,
            generation_model_revision=metadata.get("model_revision_id"),
        )
