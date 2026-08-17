from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_api.artifact_engine.contracts import VersionCreateCommand
from lumi_api.artifact_engine.ports import (
    ArtifactHeadConflict,
    ArtifactRuntimeRepository,
)
from lumi_api.artifact_engine.service import ArtifactEngineService
from lumi_api.artifacts.models import (
    CreatedByType,
    LineageEdgeType,
)
from lumi_api.domain.ids import new_uuid7
from lumi_auto_repair import (
    RepairCandidate,
    RepairQualitySnapshot,
    RepairSourceSnapshot,
    RepairStaleConflict,
)


class Node42RepairArtifactAdapter:
    def __init__(
        self,
        *,
        service: ArtifactEngineService,
        repository: ArtifactRuntimeRepository,
    ) -> None:
        self.service = service
        self.repository = repository

    def load_source_exact(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> RepairSourceSnapshot:
        version = self.repository.get_version(UUID(artifact_version_id))
        artifact = self.repository.get_artifact(version.artifact_id)
        branch = self.repository.get_branch(version.branch_id)
        if str(version.id) != artifact_version_id:
            raise ValueError("REPAIR_EXACT_ARTIFACT_VERSION_MISMATCH")
        if str(version.organization_id) != organization_id:
            raise PermissionError("REPAIR_ARTIFACT_ORGANIZATION_MISMATCH")
        if str(artifact.project_id) != project_id:
            raise PermissionError("REPAIR_ARTIFACT_PROJECT_MISMATCH")
        if branch.head_version_id is None:
            raise ValueError("REPAIR_BRANCH_HEAD_REQUIRED")
        primary = None
        if version.primary_file_id is not None:
            primary = next(
                (
                    item
                    for item in version.files
                    if item.id == version.primary_file_id
                ),
                None,
            )
        metadata = dict(primary.metadata) if primary is not None else {}
        protected_refs = _csv_refs(metadata.get("protected_refs"))
        return RepairSourceSnapshot(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=str(artifact.id),
            artifact_version_id=str(version.id),
            artifact_content_hash=version.content_hash,
            artifact_type=artifact.type.value,
            original_branch_id=str(version.branch_id),
            original_head_version_id=str(branch.head_version_id),
            design_document_id=(
                str(artifact.design_document_id)
                if artifact.design_document_id is not None
                else None
            ),
            design_document_version_id=(
                str(version.design_document_version_id)
                if version.design_document_version_id is not None
                else None
            ),
            constraint_snapshot_hash=version.constraint_snapshot_hash,
            protected_refs=protected_refs,
        )

    def fork_repair_branch(
        self,
        *,
        source: RepairSourceSnapshot,
        repair_job_id: str,
        iteration: int,
        actor_id: str,
    ) -> str:
        branch = self.service.fork_version(
            UUID(source.artifact_version_id),
            name=f"repair-{repair_job_id[:8]}-{iteration}",
            created_by_type=CreatedByType.SYSTEM,
            created_by_id=f"auto-repair:{actor_id}"[:200],
            created_at=datetime.now(UTC),
        )
        return str(branch.id)

    def promote_candidate(
        self,
        *,
        original_source: RepairSourceSnapshot,
        candidate: RepairCandidate,
        quality: RepairQualitySnapshot,
        repair_job_id: str,
        actor_id: str,
    ) -> str:
        source = self.repository.get_version(
            UUID(candidate.artifact_version_id)
        )
        if str(source.artifact_id) != original_source.artifact_id:
            raise ValueError("REPAIR_PROMOTION_ARTIFACT_MISMATCH")
        envelope = self.repository.get_provenance_envelope(source.id)
        inputs = tuple(
            dict.fromkeys(
                (
                    *envelope.record.input_artifact_version_ids,
                    source.id,
                )
            )
        )
        provenance = envelope.model_copy(
            update={
                "record": envelope.record.model_copy(
                    update={
                        "input_artifact_version_ids": inputs,
                    }
                ),
                "agent_version": "auto-repair/1.0.0",
            }
        )
        cloned_files = tuple(
            item.model_copy(update={"id": new_uuid7()})
            for item in source.files
        )
        primary_file_id = None
        if source.primary_file_id is not None:
            for original, cloned in zip(
                source.files,
                cloned_files,
                strict=True,
            ):
                if original.id == source.primary_file_id:
                    primary_file_id = cloned.id
                    break
        try:
            promoted, _ = self.service.create_version(
                VersionCreateCommand(
                    branch_id=UUID(original_source.original_branch_id),
                    expected_head_version_id=UUID(
                        original_source.original_head_version_id
                    ),
                    content_hash=source.content_hash,
                    files=cloned_files,
                    provenance=provenance,
                    rights=source.rights,
                    created_by_type=CreatedByType.SYSTEM,
                    created_by_id=(
                        f"auto-repair:{repair_job_id}:{actor_id}"
                    )[:200],
                    created_at=datetime.now(UTC),
                    primary_file_id=primary_file_id,
                    design_document_version_id=(
                        source.design_document_version_id
                    ),
                    quality_score=quality.overall_score / 100,
                    constraint_snapshot_hash=(
                        source.constraint_snapshot_hash
                    ),
                    lineage_sources=(
                        (
                            source.id,
                            LineageEdgeType.EDITED_FROM,
                        ),
                    ),
                )
            )
        except ArtifactHeadConflict as exc:
            raise RepairStaleConflict(
                "REPAIR_MAIN_BRANCH_HEAD_CHANGED"
            ) from exc
        now = datetime.now(UTC)
        ready = self.service.mark_ready(promoted.id, occurred_at=now)
        approved, _ = self.service.approve_version(
            ready.id,
            approved_by_id=f"auto-repair:{repair_job_id}"[:200],
            approved_at=now,
            validation_ref=(
                f"quality-result:{quality.quality_result_id}"
            ),
        )
        return str(approved.id)


def _csv_refs(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(
            sorted(item.strip() for item in value.split(",") if item.strip())
        )
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(sorted(str(item) for item in value if str(item)))
    return (str(value),)
