from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from lumi_image_edit import (
    ArtifactEditResult,
    EditProvenance,
    EditValidationReport,
    ImageEditSpec,
    ValidatedImage,
)
from lumi_api.artifact_engine.contracts import ProvenanceEnvelope, VersionCreateCommand
from lumi_api.artifact_engine.service import ArtifactEngineService
from lumi_api.artifacts.models import (
    ArtifactFile,
    CreatedByType,
    FileRole,
    LineageEdgeType,
    ProvenanceRecord,
    SkillVersionRef,
)
from lumi_api.domain.ids import new_uuid7


class ArtifactAssetProjectionPort(Protocol):
    def project(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_version_id: UUID,
        candidate_asset_id: UUID | None,
    ) -> UUID: ...


class Node42ImageEditArtifactAdapter:
    """Append-only edit versions; rejected candidates never advance a requested branch."""

    def __init__(
        self,
        service: ArtifactEngineService,
        asset_projection: ArtifactAssetProjectionPort,
    ) -> None:
        self.service = service
        self.asset_projection = asset_projection

    async def append_candidate(
        self,
        *,
        spec: ImageEditSpec,
        image: ValidatedImage,
        provenance: EditProvenance,
        validation: EditValidationReport,
    ) -> ArtifactEditResult:
        source_id = UUID(spec.source.artifact_version_id)
        source = self.service.repository.get_version(source_id)
        if str(source.artifact_id) != spec.source.artifact_id or str(source.organization_id) != spec.organization_id:
            raise ValueError("IMAGE_EDIT_ARTIFACT_SOURCE_SCOPE_MISMATCH")
        if source.content_hash != spec.source.checksum_sha256:
            raise ValueError("IMAGE_EDIT_ARTIFACT_SOURCE_HASH_CHANGED")

        now = datetime.now(UTC)
        file_id = new_uuid7()
        created_type = CreatedByType.AGENT if spec.agent_run_id else CreatedByType.SYSTEM
        created_id = spec.agent_run_id
        artifact_file = ArtifactFile(
            id=file_id,
            role=FileRole.ORIGINAL,
            bucket=image.bucket,
            storage_key=image.storage_key,
            mime_type=image.mime_type,
            size_bytes=image.size_bytes,
            checksum_sha256=image.checksum_sha256,
            width=image.width,
            height=image.height,
            metadata=(
                ("image_edit_id", provenance.edit_id),
                ("image_edit_provenance", provenance.snapshot_id),
                ("validation_decision", validation.decision),
                ("mask_hash", provenance.mask_hash or "none"),
            ),
        )
        record = ProvenanceRecord(
            agent_run_id=UUID(spec.agent_run_id) if spec.agent_run_id else None,
            task_id=UUID(spec.task_id),
            provider=provenance.provider,
            model=provenance.model,
            provider_request_id=provenance.provider_request_id,
            prompt_hash=provenance.instruction_hash,
            prompt_ref=f"image-edit:{provenance.edit_id}",
            input_asset_ids=(UUID(spec.source.asset_id),),
            input_artifact_version_ids=(source_id,),
            constraint_snapshot_hash=provenance.constraint_snapshot_hash,
            recipe_version=spec.recipe_version,
            skill_versions=tuple(
                SkillVersionRef(skill_id=skill_id, version=version)
                for skill_id, version in sorted(spec.skill_versions.items())
            ),
            code_git_sha=provenance.code_git_sha,
        )

        target_branch_id = source.branch_id
        expected_head = source.id
        if spec.target_branch_id is not None:
            requested = self.service.repository.get_branch(UUID(spec.target_branch_id))
            if requested.organization_id != source.organization_id:
                raise PermissionError("IMAGE_EDIT_TARGET_BRANCH_ORG_MISMATCH")
            if requested.artifact_id != source.artifact_id:
                raise ValueError("IMAGE_EDIT_TARGET_BRANCH_ARTIFACT_MISMATCH")
            if requested.head_version_id != source.id:
                raise ValueError("IMAGE_EDIT_TARGET_BRANCH_HEAD_MISMATCH")
            target_branch_id = requested.id

        if validation.decision != "PASS":
            branch = self.service.fork_version(
                source.id,
                name=f"image-edit-{validation.decision.lower()}-{provenance.edit_id[:8]}",
                created_by_type=created_type,
                created_by_id=created_id,
                created_at=now,
            )
            target_branch_id = branch.id
            expected_head = source.id

        version, _ = self.service.create_version(
            VersionCreateCommand(
                branch_id=target_branch_id,
                expected_head_version_id=expected_head,
                content_hash=image.checksum_sha256,
                files=(artifact_file,),
                provenance=ProvenanceEnvelope(
                    record=record,
                    compiler_version="image-edit/1.0.0",
                    agent_version=spec.agent_version,
                ),
                rights=source.rights,
                created_by_type=created_type,
                created_by_id=created_id,
                created_at=now,
                primary_file_id=file_id,
                constraint_snapshot_hash=provenance.constraint_snapshot_hash,
                lineage_sources=((source.id, LineageEdgeType.EDITED_FROM),),
            )
        )
        status = version.status.value
        if validation.decision == "PASS":
            status = self.service.mark_ready(version.id, occurred_at=now).status.value

        candidate_asset_id = UUID(image.asset_id) if image.asset_id else None
        asset_id = self.asset_projection.project(
            organization_id=source.organization_id,
            project_id=UUID(spec.project_id),
            artifact_version_id=version.id,
            candidate_asset_id=candidate_asset_id,
        )
        return ArtifactEditResult(
            str(source.artifact_id),
            str(version.id),
            status,
            str(asset_id),
        )
