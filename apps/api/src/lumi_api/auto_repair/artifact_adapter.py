from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_api.artifact_engine.contracts import ArtifactOutboxEvent
from lumi_api.artifact_engine.ports import ArtifactHeadConflict, ArtifactRuntimeRepository
from lumi_api.artifact_engine.service import ArtifactEngineService, evaluate_provenance_completeness
from lumi_api.artifacts.models import (
    ArtifactVersion,
    ArtifactVersionStatus,
    CreatedByType,
    LineageEdge,
    LineageEdgeType,
)
from lumi_api.domain.ids import new_uuid7
from lumi_auto_repair import (
    RepairCandidate,
    RepairQualitySnapshot,
    RepairSourceSnapshot,
    RepairStaleConflict,
)

from .staged_artifact_repository import PostgresStagedArtifactRepository

_PASS_QUALITY = {"PASS", "PASS_WITH_WARNINGS"}


class Node42RepairArtifactAdapter:
    def __init__(
        self,
        *,
        service: ArtifactEngineService,
        repository: ArtifactRuntimeRepository,
        staged_repository: PostgresStagedArtifactRepository,
    ) -> None:
        self.service = service
        self.repository = repository
        self.staged_repository = staged_repository

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
                (item for item in version.files if item.id == version.primary_file_id),
                None,
            )
        metadata = dict(primary.metadata) if primary is not None else {}
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
            protected_refs=_csv_refs(metadata.get("protected_refs")),
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
        repair_job_id: str,
        actor_id: str,
    ) -> RepairCandidate:
        source = self.repository.get_version(UUID(candidate.artifact_version_id))
        if str(source.artifact_id) != original_source.artifact_id:
            raise ValueError("REPAIR_PROMOTION_ARTIFACT_MISMATCH")
        if source.content_hash != candidate.artifact_content_hash:
            raise ValueError("REPAIR_PROMOTION_CANDIDATE_HASH_MISMATCH")
        envelope = self.repository.get_provenance_envelope(source.id)
        inputs = tuple(
            dict.fromkeys((*envelope.record.input_artifact_version_ids, source.id))
        )
        provenance = envelope.model_copy(
            update={
                "record": envelope.record.model_copy(
                    update={"input_artifact_version_ids": inputs}
                ),
                "agent_version": "auto-repair/1.0.0",
            }
        )
        completeness = evaluate_provenance_completeness(
            provenance,
            created_by_type=CreatedByType.SYSTEM,
        )
        cloned_files = tuple(
            item.model_copy(update={"id": new_uuid7()}) for item in source.files
        )
        primary_file_id = None
        if source.primary_file_id is not None:
            for original, cloned in zip(source.files, cloned_files, strict=True):
                if original.id == source.primary_file_id:
                    primary_file_id = cloned.id
                    break
        branch_id = UUID(original_source.original_branch_id)
        expected_head = UUID(original_source.original_head_version_id)
        staged_id = new_uuid7()
        now = datetime.now(UTC)

        def version_factory(branch, number: int) -> ArtifactVersion:
            return ArtifactVersion(
                id=staged_id,
                organization_id=source.organization_id,
                artifact_id=source.artifact_id,
                branch_id=branch.id,
                parent_version_id=branch.head_version_id,
                version_number=number,
                status=ArtifactVersionStatus.DRAFT,
                content_hash=source.content_hash,
                primary_file_id=primary_file_id,
                design_document_version_id=source.design_document_version_id,
                quality_score=None,
                constraint_snapshot_hash=source.constraint_snapshot_hash,
                created_by_type=CreatedByType.SYSTEM,
                created_by_id=f"auto-repair:{repair_job_id}:{actor_id}"[:200],
                created_at=now,
                files=cloned_files,
                provenance=provenance.record,
                rights=source.rights,
            )

        def lineage_factory(version: ArtifactVersion) -> tuple[LineageEdge, ...]:
            return (
                LineageEdge(
                    id=new_uuid7(),
                    organization_id=version.organization_id,
                    artifact_version_id=version.id,
                    source_artifact_version_id=source.id,
                    type=LineageEdgeType.EDITED_FROM,
                    created_at=now,
                ),
            )

        def event_factory(version: ArtifactVersion) -> ArtifactOutboxEvent:
            return ArtifactOutboxEvent(
                id=new_uuid7(),
                organization_id=version.organization_id,
                event_type="artifact.version.staged",
                aggregate_id=version.artifact_id,
                aggregate_version_id=version.id,
                occurred_at=now,
                payload={
                    "branch_id": str(version.branch_id),
                    "expected_head_version_id": str(expected_head),
                    "repair_job_id": repair_job_id,
                },
            )

        try:
            staged, _ = self.staged_repository.stage_version(
                branch_id=branch_id,
                expected_head_version_id=expected_head,
                version_factory=version_factory,
                lineage_factory=lineage_factory,
                provenance=provenance,
                completeness=completeness,
                event_factory=event_factory,
            )
        except ArtifactHeadConflict as exc:
            raise RepairStaleConflict("REPAIR_MAIN_BRANCH_HEAD_CHANGED") from exc
        return RepairCandidate(
            artifact_version_id=str(staged.id),
            artifact_content_hash=staged.content_hash,
            repair_branch_id=str(staged.branch_id),
            changed_node_ids=candidate.changed_node_ids,
            metadata={
                "promotion_source_candidate_version_id": candidate.artifact_version_id,
                "promotion_state": "STAGED_NOT_HEAD",
            },
        )

    def approve_promoted_version(
        self,
        *,
        promoted: RepairCandidate,
        quality: RepairQualitySnapshot,
        repair_job_id: str,
    ) -> str:
        if quality.artifact_version_id != promoted.artifact_version_id:
            raise ValueError("REPAIR_PROMOTION_QUALITY_VERSION_MISMATCH")
        if quality.status not in _PASS_QUALITY:
            raise ValueError("REPAIR_PROMOTION_QUALITY_NOT_PASSING")
        version = self.repository.get_version(UUID(promoted.artifact_version_id))
        if version.content_hash != promoted.artifact_content_hash:
            raise ValueError("REPAIR_PROMOTION_CONTENT_HASH_MISMATCH")
        now = datetime.now(UTC)
        ready = self.service.mark_ready(version.id, occurred_at=now)
        approved, _ = self.service.approve_version(
            ready.id,
            approved_by_id=f"auto-repair:{repair_job_id}"[:200],
            approved_at=now,
            validation_ref=f"quality-result:{quality.quality_result_id}",
        )
        try:
            self.staged_repository.advance_head_to_staged(
                branch_id=approved.branch_id,
                expected_head_version_id=approved.parent_version_id,
                staged_version_id=approved.id,
                event=ArtifactOutboxEvent(
                    id=new_uuid7(),
                    organization_id=approved.organization_id,
                    event_type="artifact.branch.head.promoted",
                    aggregate_id=approved.artifact_id,
                    aggregate_version_id=approved.id,
                    occurred_at=now,
                    payload={
                        "repair_job_id": repair_job_id,
                        "validation_ref": f"quality-result:{quality.quality_result_id}",
                    },
                ),
            )
        except ArtifactHeadConflict as exc:
            raise RepairStaleConflict("REPAIR_MAIN_BRANCH_HEAD_CHANGED") from exc
        return str(approved.id)


def _csv_refs(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(sorted(item.strip() for item in value.split(",") if item.strip()))
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(sorted(str(item) for item in value if str(item)))
    return (str(value),)
