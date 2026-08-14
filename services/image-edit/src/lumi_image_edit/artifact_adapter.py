from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from lumi_artifacts.history import ArtifactHistory, ArtifactHistoryError
from lumi_artifacts.model import ArtifactFile, ArtifactVersion, LineageEdge, ProvenanceRecord
from lumi_artifacts.runtime import advance_branch_head_cas, next_version_number

from .model import EditProvenanceSnapshot, EditValidationReport, ImageEditSpec
from .ports import ArtifactEditResult, StoredEditedImage


class ArtifactHistoryImageEditAdapter:
    """NODE-42 append-only edit adapter. Rejected/repair versions never advance branch head."""

    def __init__(self, history: ArtifactHistory) -> None:
        self.history = history
        self.edit_provenance: dict[str, EditProvenanceSnapshot] = {}

    async def create_version(
        self,
        *,
        spec: ImageEditSpec,
        candidate: StoredEditedImage,
        provenance: EditProvenanceSnapshot,
        validation: EditValidationReport,
    ) -> ArtifactEditResult:
        source = self.history.versions.get(spec.source.artifact_version_id)
        if source is None:
            raise ArtifactHistoryError("IMAGE_EDIT_SOURCE_ARTIFACT_VERSION_MISSING")
        if source.organization_id != spec.organization_id or source.artifact_id != spec.source.artifact_id:
            raise ArtifactHistoryError("IMAGE_EDIT_SOURCE_ARTIFACT_TENANT_OR_ID_MISMATCH")
        branch = self.history.branches[source.branch_id]
        if branch.head_version_id != source.id:
            raise ArtifactHistoryError("IMAGE_EDIT_SOURCE_IS_STALE_BRANCH_HEAD")

        version_id = f"artifact-version:edit:{provenance.edit_id}"
        existing = self.history.versions.get(version_id)
        if existing is not None:
            return ArtifactEditResult(artifact_version_id=version_id, status=existing.status)
        file_id = f"artifact-file:edit:{provenance.edit_id}"
        version = ArtifactVersion(
            id=version_id,
            organization_id=source.organization_id,
            artifact_id=source.artifact_id,
            branch_id=source.branch_id,
            parent_version_id=source.id,
            schema_version=source.schema_version,
            version_number=next_version_number(self.history, source.artifact_id),
            status="DRAFT",
            content_hash=candidate.checksum_sha256,
            constraint_snapshot_hash=provenance.constraint_snapshot_hash,
            created_by_type="AGENT",
            created_by_id=spec.agent_run_id or spec.task_id,
            created_at=datetime.now(timezone.utc),
            primary_file_id=file_id,
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
        )
        self.history.add_version(version, advance_branch_head=False)
        self.history.add_file(ArtifactFile(
            id=file_id,
            organization_id=source.organization_id,
            artifact_version_id=version_id,
            role="ORIGINAL",
            storage_key=candidate.storage_key,
            mime_type=candidate.mime_type,
            size_bytes=candidate.size_bytes,
            checksum_sha256=candidate.checksum_sha256,
            width=candidate.width,
            height=candidate.height,
            metadata={"image_edit_provenance_snapshot_id": provenance.snapshot_id},
        ))
        self.history.add_provenance(ProvenanceRecord(
            artifact_version_id=version_id,
            organization_id=source.organization_id,
            constraint_snapshot_hash=provenance.constraint_snapshot_hash,
            code_git_sha=spec.code_git_sha,
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
            agent_run_id=spec.agent_run_id,
            task_id=spec.task_id,
            provider=provenance.provider,
            model=provenance.model,
            provider_request_id=provenance.provider_request_id,
            prompt_hash=provenance.instruction_hash,
            input_asset_ids=(spec.source.asset_id,),
            input_artifact_version_ids=(source.id,),
            recipe_version=spec.recipe_version,
        ))
        self.history.add_edge(LineageEdge(
            id=f"artifact-edge:edit:{provenance.edit_id}",
            organization_id=source.organization_id,
            from_version_id=source.id,
            to_version_id=version_id,
            type="EDITED_FROM",
            metadata={
                "route": provenance.route,
                "mask_hash": provenance.mask_hash,
                "protected_region_hash": provenance.protected_region_hash,
                "provenance_snapshot_id": provenance.snapshot_id,
            },
        ))
        self.edit_provenance[provenance.snapshot_id] = provenance

        if validation.decision == "PASS":
            ready = self.history.transition_status(version_id, "READY")
            advance_branch_head_cas(
                self.history,
                branch_id=source.branch_id,
                expected_head_version_id=source.id,
                next_head_version_id=version_id,
            )
            status = ready.status
        elif validation.decision == "REJECT":
            status = self.history.transition_status(version_id, "REJECTED").status
        else:
            status = "DRAFT"
        self.history.validate_integrity()
        return ArtifactEditResult(artifact_version_id=version_id, status=status)
