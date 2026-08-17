from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from lumi_api.artifacts.engine import (
    ArtifactContractError,
    ArtifactGraphViolation,
    fork_branch,
    transition_version_status,
)
from lumi_api.artifacts.models import (
    Artifact,
    ArtifactBranch,
    ArtifactFile,
    ArtifactType,
    ArtifactVersion,
    ArtifactVersionStatus,
    CreatedByType,
    LineageEdge,
    LineageEdgeType,
)
from lumi_api.domain.ids import new_uuid7

from .contracts import (
    ApprovalRecord,
    ArtifactCompareKind,
    ArtifactCompareResult,
    ArtifactCreateCommand,
    ArtifactOutboxEvent,
    GcAudit,
    GcMark,
    GcMarkState,
    ProvenanceCompleteness,
    ProvenanceEnvelope,
    TraceabilityStatus,
    VersionCreateCommand,
)
from .ports import (
    ArtifactRuntimeRepository,
    ArtifactStoragePort,
    ArtifactStorageViolation,
    DesignDocumentReader,
    DesignSemanticDiffPort,
    RasterVisualDiffPort,
)


def _event(
    *,
    organization_id: UUID,
    event_type: str,
    aggregate_id: UUID,
    occurred_at: datetime,
    aggregate_version_id: UUID | None = None,
    payload: dict | None = None,
) -> ArtifactOutboxEvent:
    return ArtifactOutboxEvent(
        id=new_uuid7(),
        organization_id=organization_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        aggregate_version_id=aggregate_version_id,
        occurred_at=occurred_at,
        payload=payload or {},
    )


def evaluate_provenance_completeness(
    envelope: ProvenanceEnvelope,
    *,
    created_by_type: CreatedByType,
) -> ProvenanceCompleteness:
    record = envelope.record
    checks: list[tuple[str, bool]] = [
        ("code_git_sha", bool(record.code_git_sha)),
        ("compiler_version", bool(envelope.compiler_version)),
        ("constraint_snapshot_hash", bool(record.constraint_snapshot_hash)),
    ]
    if created_by_type == CreatedByType.AGENT:
        checks.extend(
            [
                ("agent_run_or_task", bool(record.agent_run_id or record.task_id)),
                ("agent_version", bool(envelope.agent_version)),
                (
                    "recipe_or_skill_versions",
                    bool(record.recipe_version or record.skill_versions),
                ),
            ]
        )
    if record.generation_id is not None:
        checks.extend(
            [
                ("provider", bool(record.provider)),
                ("model", bool(record.model)),
                ("prompt_hash", bool(record.prompt_hash)),
                (
                    "prompt_template_version",
                    bool(record.prompt_template_version),
                ),
            ]
        )
    missing = tuple(name for name, passed in checks if not passed)
    score = 1.0 if not checks else sum(1 for _, passed in checks if passed) / len(checks)
    return ProvenanceCompleteness(
        score=score,
        status=(
            TraceabilityStatus.FULLY_TRACEABLE
            if not missing
            else TraceabilityStatus.PARTIAL
        ),
        missing_fields=missing,
    )


class ArtifactEngineService:
    def __init__(
        self,
        repository: ArtifactRuntimeRepository,
        storage: ArtifactStoragePort,
        *,
        design_reader: DesignDocumentReader | None = None,
        semantic_diff: DesignSemanticDiffPort | None = None,
        visual_diff: RasterVisualDiffPort | None = None,
        require_full_traceability_for_approval: bool = False,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.design_reader = design_reader
        self.semantic_diff = semantic_diff
        self.visual_diff = visual_diff
        self.require_full_traceability_for_approval = (
            require_full_traceability_for_approval
        )

    def create_artifact(self, command: ArtifactCreateCommand) -> tuple[Artifact, ArtifactBranch]:
        artifact = Artifact(
            id=new_uuid7(),
            organization_id=command.organization_id,
            project_id=command.project_id,
            type=command.artifact_type,
            name=command.name,
            design_document_id=command.design_document_id,
            rights=command.rights,
        )
        branch = ArtifactBranch(
            id=new_uuid7(),
            organization_id=command.organization_id,
            artifact_id=artifact.id,
            name="main",
            base_version_id=None,
            head_version_id=None,
            created_by_type=command.created_by_type,
            created_by_id=command.created_by_id,
            created_at=command.created_at,
        )
        created_event = _event(
            organization_id=artifact.organization_id,
            event_type="artifact.created",
            aggregate_id=artifact.id,
            occurred_at=command.created_at,
            payload={"branch_id": str(branch.id), "artifact_type": artifact.type.value},
        )
        initial = command.initial_version
        if initial is None:
            self.repository.create_artifact_bundle(artifact, branch, created_event)
            return artifact, branch

        self._validate_version_payload(
            organization_id=artifact.organization_id,
            files=initial.files,
            primary_file_id=initial.primary_file_id,
            constraint_snapshot_hash=initial.constraint_snapshot_hash,
            provenance=initial.provenance,
        )
        for source_id, _ in initial.lineage_sources:
            source = self.repository.get_version(source_id)
            if source.organization_id != artifact.organization_id:
                raise ArtifactGraphViolation("lineage source crosses organization boundary")
        completeness = evaluate_provenance_completeness(
            initial.provenance,
            created_by_type=initial.created_by_type,
        )
        version = ArtifactVersion(
            id=new_uuid7(),
            organization_id=artifact.organization_id,
            artifact_id=artifact.id,
            branch_id=branch.id,
            parent_version_id=None,
            version_number=1,
            status=ArtifactVersionStatus.DRAFT,
            content_hash=initial.content_hash,
            primary_file_id=initial.primary_file_id,
            design_document_version_id=initial.design_document_version_id,
            quality_score=initial.quality_score,
            constraint_snapshot_hash=initial.constraint_snapshot_hash,
            created_by_type=initial.created_by_type,
            created_by_id=initial.created_by_id,
            created_at=command.created_at,
            files=initial.files,
            provenance=initial.provenance.record,
            rights=initial.rights,
        )
        lineage = tuple(
            LineageEdge(
                id=new_uuid7(),
                organization_id=artifact.organization_id,
                artifact_version_id=version.id,
                source_artifact_version_id=source_id,
                type=edge_type,
                created_at=command.created_at,
            )
            for source_id, edge_type in sorted(
                dict.fromkeys(initial.lineage_sources),
                key=lambda item: (item[1].value, str(item[0])),
            )
        )
        version_event = _event(
            organization_id=artifact.organization_id,
            event_type="artifact.version.created",
            aggregate_id=artifact.id,
            aggregate_version_id=version.id,
            occurred_at=command.created_at,
            payload={
                "branch_id": str(branch.id),
                "version_number": 1,
                "traceability": completeness.status.value,
                "traceability_score": float(completeness.score),
            },
        )
        self.repository.create_artifact_bundle_with_initial_version(
            artifact,
            branch,
            version,
            lineage,
            initial.provenance,
            completeness,
            (created_event, version_event),
        )
        return artifact, branch.model_copy(
            update={"base_version_id": version.id, "head_version_id": version.id}
        )

    def create_version(
        self, command: VersionCreateCommand
    ) -> tuple[ArtifactVersion, tuple[LineageEdge, ...]]:
        branch = self.repository.get_branch(command.branch_id)
        artifact = self.repository.get_artifact(branch.artifact_id)
        if branch.organization_id != artifact.organization_id:
            raise ArtifactGraphViolation("artifact branch crosses organization boundary")
        self._validate_version_payload(
            organization_id=branch.organization_id,
            files=command.files,
            primary_file_id=command.primary_file_id,
            constraint_snapshot_hash=command.constraint_snapshot_hash,
            provenance=command.provenance,
        )
        for source_id, _ in command.lineage_sources:
            source = self.repository.get_version(source_id)
            if source.organization_id != branch.organization_id:
                raise ArtifactGraphViolation("lineage source crosses organization boundary")
        completeness = evaluate_provenance_completeness(
            command.provenance,
            created_by_type=command.created_by_type,
        )
        version_id = new_uuid7()

        def version_factory(current_branch: ArtifactBranch, number: int) -> ArtifactVersion:
            return ArtifactVersion(
                id=version_id,
                organization_id=current_branch.organization_id,
                artifact_id=current_branch.artifact_id,
                branch_id=current_branch.id,
                parent_version_id=current_branch.head_version_id,
                version_number=number,
                status=ArtifactVersionStatus.DRAFT,
                content_hash=command.content_hash,
                primary_file_id=command.primary_file_id,
                design_document_version_id=command.design_document_version_id,
                quality_score=command.quality_score,
                constraint_snapshot_hash=command.constraint_snapshot_hash,
                created_by_type=command.created_by_type,
                created_by_id=command.created_by_id,
                created_at=command.created_at,
                files=command.files,
                provenance=command.provenance.record,
                rights=command.rights,
            )

        def lineage_factory(version: ArtifactVersion) -> tuple[LineageEdge, ...]:
            requested: list[tuple[UUID, LineageEdgeType]] = list(command.lineage_sources)
            if version.parent_version_id is not None:
                requested.append((version.parent_version_id, LineageEdgeType.EDITED_FROM))
            unique: dict[tuple[UUID, LineageEdgeType], None] = {}
            for item in requested:
                unique[item] = None
            return tuple(
                LineageEdge(
                    id=new_uuid7(),
                    organization_id=version.organization_id,
                    artifact_version_id=version.id,
                    source_artifact_version_id=source_id,
                    type=edge_type,
                    created_at=command.created_at,
                )
                for source_id, edge_type in sorted(
                    unique,
                    key=lambda item: (item[1].value, str(item[0])),
                )
            )

        def event_factory(version: ArtifactVersion) -> ArtifactOutboxEvent:
            return _event(
                organization_id=version.organization_id,
                event_type="artifact.version.created",
                aggregate_id=version.artifact_id,
                aggregate_version_id=version.id,
                occurred_at=command.created_at,
                payload={
                    "branch_id": str(version.branch_id),
                    "version_number": version.version_number,
                    "traceability": completeness.status.value,
                    "traceability_score": float(completeness.score),
                },
            )

        return self.repository.append_version(
            branch_id=command.branch_id,
            expected_head_version_id=command.expected_head_version_id,
            version_factory=version_factory,
            lineage_factory=lineage_factory,
            provenance=command.provenance,
            completeness=completeness,
            event_factory=event_factory,
        )

    def mark_ready(self, version_id: UUID, *, occurred_at: datetime) -> ArtifactVersion:
        current = self.repository.get_version(version_id)
        updated = transition_version_status(current, ArtifactVersionStatus.READY)
        self.repository.replace_version_status(
            updated,
            expected_status=current.status.value,
            approval=None,
            event=_event(
                organization_id=current.organization_id,
                event_type="artifact.version.ready",
                aggregate_id=current.artifact_id,
                aggregate_version_id=current.id,
                occurred_at=occurred_at,
            ),
        )
        return updated

    def approve_version(
        self,
        version_id: UUID,
        *,
        approved_by_id: str,
        approved_at: datetime,
        validation_ref: str,
    ) -> tuple[ArtifactVersion, ApprovalRecord]:
        current = self.repository.get_version(version_id)
        completeness = self.repository.get_provenance_completeness(version_id)
        if (
            self.require_full_traceability_for_approval
            and completeness.status != TraceabilityStatus.FULLY_TRACEABLE
        ):
            raise ArtifactContractError(
                "approval policy requires fully traceable provenance"
            )
        updated = transition_version_status(
            current,
            ArtifactVersionStatus.APPROVED,
            validation_passed=True,
        )
        approval = ApprovalRecord(
            id=new_uuid7(),
            organization_id=current.organization_id,
            artifact_version_id=current.id,
            approved_by_id=approved_by_id,
            approved_at=approved_at,
            validation_ref=validation_ref,
        )
        self.repository.replace_version_status(
            updated,
            expected_status=current.status.value,
            approval=approval,
            event=_event(
                organization_id=current.organization_id,
                event_type="artifact.version.approved",
                aggregate_id=current.artifact_id,
                aggregate_version_id=current.id,
                occurred_at=approved_at,
                payload={"approval_id": str(approval.id)},
            ),
        )
        return updated, approval

    def fork_version(
        self,
        version_id: UUID,
        *,
        name: str,
        created_by_type: CreatedByType,
        created_by_id: str | None,
        created_at: datetime,
    ) -> ArtifactBranch:
        source = self.repository.get_version(version_id)
        branch = fork_branch(
            source,
            branch_id=new_uuid7(),
            name=name,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
            created_at=created_at,
        )
        self.repository.create_branch(
            branch,
            _event(
                organization_id=source.organization_id,
                event_type="artifact.branch.forked",
                aggregate_id=source.artifact_id,
                aggregate_version_id=source.id,
                occurred_at=created_at,
                payload={"branch_id": str(branch.id), "branch_name": branch.name},
            ),
        )
        return branch

    def restore_version(
        self,
        source_version_id: UUID,
        *,
        target_branch_id: UUID,
        expected_head_version_id: UUID | None,
        provenance: ProvenanceEnvelope,
        created_by_type: CreatedByType,
        created_by_id: str | None,
        created_at: datetime,
    ) -> tuple[ArtifactVersion, tuple[LineageEdge, ...]]:
        source = self.repository.get_version(source_version_id)
        branch = self.repository.get_branch(target_branch_id)
        if source.organization_id != branch.organization_id:
            raise ArtifactGraphViolation("restore cannot cross organizations")
        if source.artifact_id != branch.artifact_id:
            raise ArtifactGraphViolation("restore source must belong to the same artifact")
        if source.id not in provenance.record.input_artifact_version_ids:
            raise ArtifactContractError(
                "restore provenance must reference the restored source version"
            )
        cloned_files, primary_file_id = self._clone_files(
            source.files,
            source.primary_file_id,
        )
        return self.create_version(
            VersionCreateCommand(
                branch_id=target_branch_id,
                expected_head_version_id=expected_head_version_id,
                content_hash=source.content_hash,
                files=cloned_files,
                provenance=provenance,
                rights=source.rights,
                created_by_type=created_by_type,
                created_by_id=created_by_id,
                created_at=created_at,
                primary_file_id=primary_file_id,
                design_document_version_id=source.design_document_version_id,
                quality_score=source.quality_score,
                constraint_snapshot_hash=source.constraint_snapshot_hash,
                lineage_sources=((source.id, LineageEdgeType.DERIVED_FROM),),
            )
        )

    def compare_versions(self, left_id: UUID, right_id: UUID) -> ArtifactCompareResult:
        left = self.repository.get_version(left_id)
        right = self.repository.get_version(right_id)
        if left.organization_id != right.organization_id:
            raise ArtifactGraphViolation("artifact compare cannot cross organizations")
        left_artifact = self.repository.get_artifact(left.artifact_id)
        right_artifact = self.repository.get_artifact(right.artifact_id)
        equal_hash = left.content_hash == right.content_hash

        if (
            left_artifact.type == ArtifactType.DESIGN_DOCUMENT
            and right_artifact.type == ArtifactType.DESIGN_DOCUMENT
            and left.design_document_version_id is not None
            and right.design_document_version_id is not None
            and self.design_reader is not None
            and self.semantic_diff is not None
        ):
            before = self.design_reader.load_design_document_version(
                left.design_document_version_id
            )
            after = self.design_reader.load_design_document_version(
                right.design_document_version_id
            )
            return ArtifactCompareResult(
                left_version_id=left.id,
                right_version_id=right.id,
                kind=ArtifactCompareKind.DESIGN_SEMANTIC,
                equal_content_hash=equal_hash,
                semantic_diff=self.semantic_diff.compare(before, after),
            )

        if (
            left_artifact.type == ArtifactType.RASTER_IMAGE
            and right_artifact.type == ArtifactType.RASTER_IMAGE
        ):
            left_file = self._primary_file(left)
            right_file = self._primary_file(right)
            metrics = None
            if self.visual_diff is not None:
                left_object = self.storage.stat_object(
                    left.organization_id, left_file.bucket, left_file.storage_key
                )
                right_object = self.storage.stat_object(
                    right.organization_id, right_file.bucket, right_file.storage_key
                )
                if left_object is not None and right_object is not None:
                    metrics = self.visual_diff.compare(left_object, right_object)
            return ArtifactCompareResult(
                left_version_id=left.id,
                right_version_id=right.id,
                kind=ArtifactCompareKind.RASTER_METADATA,
                equal_content_hash=equal_hash,
                visual_metrics=metrics,
                metadata={
                    "left_dimensions": [left_file.width, left_file.height],
                    "right_dimensions": [right_file.width, right_file.height],
                    "left_mime": left_file.mime_type,
                    "right_mime": right_file.mime_type,
                },
            )

        return ArtifactCompareResult(
            left_version_id=left.id,
            right_version_id=right.id,
            kind=ArtifactCompareKind.GENERIC_METADATA,
            equal_content_hash=equal_hash,
            metadata={
                "left_status": left.status.value,
                "right_status": right.status.value,
                "left_files": len(left.files),
                "right_files": len(right.files),
            },
        )

    def mark_gc_candidates(
        self,
        organization_id: UUID,
        *,
        marked_at: datetime,
        delay: timedelta,
    ) -> tuple[GcMark, ...]:
        if delay <= timedelta(0):
            raise ValueError("GC delay must be positive")
        protected = self.repository.protected_storage_locations(organization_id)
        marks = tuple(
            GcMark(
                id=new_uuid7(),
                organization_id=organization_id,
                bucket=item.bucket,
                storage_key=item.storage_key,
                checksum_sha256=item.checksum_sha256,
                marked_at=marked_at,
                not_before=marked_at + delay,
            )
            for item in sorted(
                self.storage.list_objects(organization_id),
                key=lambda value: (value.bucket, value.storage_key),
            )
            if item.location not in protected
        )
        self.repository.record_gc_marks(marks)
        return marks

    def sweep_gc(self, organization_id: UUID, *, checked_at: datetime) -> tuple[GcAudit, ...]:
        protected = self.repository.protected_storage_locations(organization_id)
        audits: list[GcAudit] = []
        for mark in self.repository.pending_gc_marks(organization_id):
            if checked_at < mark.not_before:
                continue
            if mark.location in protected:
                updated = mark.model_copy(
                    update={
                        "state": GcMarkState.CANCELLED,
                        "completed_at": checked_at,
                        "reason": "reference appeared during retention delay",
                    }
                )
                audit = self._gc_audit(updated, checked_at, "CANCELLED")
                self.repository.complete_gc_mark(updated, audit)
                audits.append(audit)
                continue
            self.storage.delete_object(
                organization_id, mark.bucket, mark.storage_key
            )
            updated = mark.model_copy(
                update={
                    "state": GcMarkState.DELETED,
                    "completed_at": checked_at,
                    "reason": "unreferenced after retention recheck",
                }
            )
            audit = self._gc_audit(updated, checked_at, "DELETED")
            self.repository.complete_gc_mark(updated, audit)
            audits.append(audit)
        return tuple(audits)

    def _validate_version_payload(
        self,
        *,
        organization_id: UUID,
        files: tuple[ArtifactFile, ...],
        primary_file_id: UUID | None,
        constraint_snapshot_hash: str | None,
        provenance: ProvenanceEnvelope,
    ) -> None:
        if primary_file_id is not None and primary_file_id not in {item.id for item in files}:
            raise ArtifactContractError(
                "primary_file_id must reference a file attached to the version"
            )
        provenance_hash = provenance.record.constraint_snapshot_hash
        if (
            constraint_snapshot_hash is not None
            and provenance_hash is not None
            and constraint_snapshot_hash != provenance_hash
        ):
            raise ArtifactContractError(
                "version and provenance constraint snapshot hashes must match"
            )
        self._verify_files(organization_id, files)

    def _verify_files(
        self,
        organization_id: UUID,
        files: tuple[ArtifactFile, ...],
    ) -> None:
        for item in files:
            stored = self.storage.stat_object(
                organization_id, item.bucket, item.storage_key
            )
            if stored is None:
                raise ArtifactStorageViolation(
                    f"storage object missing: {item.bucket}/{item.storage_key}"
                )
            if stored.organization_id != organization_id:
                raise ArtifactStorageViolation("storage object crosses organization boundary")
            if stored.checksum_sha256 != item.checksum_sha256:
                raise ArtifactStorageViolation("storage checksum does not match artifact file")
            if stored.size_bytes != item.size_bytes:
                raise ArtifactStorageViolation("storage size does not match artifact file")
            if stored.mime_type != item.mime_type:
                raise ArtifactStorageViolation("storage mime type does not match artifact file")

    @staticmethod
    def _clone_files(
        files: tuple[ArtifactFile, ...],
        primary_file_id: UUID | None,
    ) -> tuple[tuple[ArtifactFile, ...], UUID | None]:
        id_map: dict[UUID, UUID] = {}
        cloned: list[ArtifactFile] = []
        for item in files:
            new_id = new_uuid7()
            id_map[item.id] = new_id
            cloned.append(item.model_copy(update={"id": new_id}))
        return tuple(cloned), id_map.get(primary_file_id) if primary_file_id else None

    @staticmethod
    def _primary_file(version: ArtifactVersion) -> ArtifactFile:
        if version.primary_file_id is not None:
            for item in version.files:
                if item.id == version.primary_file_id:
                    return item
        if not version.files:
            raise ArtifactContractError("artifact version has no comparable file")
        return version.files[0]

    @staticmethod
    def _gc_audit(mark: GcMark, occurred_at: datetime, action: str) -> GcAudit:
        return GcAudit(
            id=new_uuid7(),
            organization_id=mark.organization_id,
            gc_mark_id=mark.id,
            action=action,
            occurred_at=occurred_at,
            bucket=mark.bucket,
            storage_key=mark.storage_key,
            checksum_sha256=mark.checksum_sha256,
            detail=mark.reason,
        )
