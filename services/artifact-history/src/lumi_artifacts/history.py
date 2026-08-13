from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from .model import Artifact, ArtifactBranch, ArtifactFile, ArtifactVersion, LineageEdge, ProvenanceRecord


class ArtifactHistoryError(ValueError):
    pass


class CrossTenantLineageError(ArtifactHistoryError):
    pass


class LineageCycleError(ArtifactHistoryError):
    pass


_ALLOWED_STATUS_TRANSITIONS = {
    "DRAFT": frozenset({"READY", "REJECTED", "ARCHIVED"}),
    "READY": frozenset({"APPROVED", "REJECTED", "ARCHIVED"}),
    "APPROVED": frozenset({"ARCHIVED"}),
    "REJECTED": frozenset({"ARCHIVED"}),
    "ARCHIVED": frozenset(),
}


class ArtifactHistory:
    """Dependency-free executable reference for NODE-15 history semantics.

    Persistence adapters may use different storage structures, but must preserve these invariants.
    """

    def __init__(self) -> None:
        self.artifacts: dict[str, Artifact] = {}
        self.branches: dict[str, ArtifactBranch] = {}
        self.versions: dict[str, ArtifactVersion] = {}
        self.files: dict[str, ArtifactFile] = {}
        self.edges: dict[str, LineageEdge] = {}
        self.provenance: dict[str, ProvenanceRecord] = {}

    def add_artifact(self, artifact: Artifact) -> None:
        if artifact.id in self.artifacts:
            raise ArtifactHistoryError(f"artifact already exists: {artifact.id}")
        self.artifacts[artifact.id] = artifact

    def add_branch(self, branch: ArtifactBranch) -> None:
        artifact = self.artifacts.get(branch.artifact_id)
        if artifact is None:
            raise ArtifactHistoryError(f"branch artifact missing: {branch.artifact_id}")
        if artifact.organization_id != branch.organization_id:
            raise ArtifactHistoryError("branch tenant does not match artifact tenant")
        if branch.id in self.branches:
            raise ArtifactHistoryError(f"branch already exists: {branch.id}")
        if any(
            other.artifact_id == branch.artifact_id and other.name == branch.name
            for other in self.branches.values()
        ):
            raise ArtifactHistoryError(f"branch name already exists for artifact: {branch.name}")
        for version_id in (branch.base_version_id, branch.head_version_id):
            if version_id is None:
                continue
            version = self.versions.get(version_id)
            if version is None or version.artifact_id != branch.artifact_id:
                raise ArtifactHistoryError(f"branch references invalid version: {version_id}")
        self.branches[branch.id] = branch

    def add_version(self, version: ArtifactVersion, *, advance_branch_head: bool = True) -> None:
        artifact = self.artifacts.get(version.artifact_id)
        branch = self.branches.get(version.branch_id)
        if artifact is None or branch is None:
            raise ArtifactHistoryError("version artifact/branch must exist")
        if artifact.organization_id != version.organization_id or branch.organization_id != version.organization_id:
            raise ArtifactHistoryError("version tenant mismatch")
        if branch.artifact_id != version.artifact_id:
            raise ArtifactHistoryError("version branch belongs to another artifact")
        if version.id in self.versions:
            raise ArtifactHistoryError(f"version already exists: {version.id}")
        if any(
            other.artifact_id == version.artifact_id
            and other.version_number == version.version_number
            for other in self.versions.values()
        ):
            raise ArtifactHistoryError(
                f"version number already used for artifact: {version.version_number}"
            )
        if version.parent_version_id is not None:
            parent = self.versions.get(version.parent_version_id)
            if parent is None:
                raise ArtifactHistoryError("parent version missing")
            if parent.artifact_id != version.artifact_id or parent.organization_id != version.organization_id:
                raise ArtifactHistoryError("parent version must belong to same artifact and tenant")
        self.versions[version.id] = version
        if advance_branch_head:
            self.branches[branch.id] = replace(branch, head_version_id=version.id)

    def add_file(self, file: ArtifactFile) -> None:
        version = self.versions.get(file.artifact_version_id)
        if version is None:
            raise ArtifactHistoryError("file version missing")
        if version.organization_id != file.organization_id:
            raise ArtifactHistoryError("file tenant mismatch")
        if file.id in self.files:
            raise ArtifactHistoryError(f"file already exists: {file.id}")
        if any(
            other.artifact_version_id == file.artifact_version_id and other.role == file.role
            for other in self.files.values()
        ):
            raise ArtifactHistoryError(f"file role already attached to version: {file.role}")
        self.files[file.id] = file

    def add_provenance(self, record: ProvenanceRecord) -> None:
        version = self.versions.get(record.artifact_version_id)
        if version is None:
            raise ArtifactHistoryError("provenance version missing")
        if version.organization_id != record.organization_id:
            raise ArtifactHistoryError("provenance tenant mismatch")
        if version.constraint_snapshot_hash != record.constraint_snapshot_hash:
            raise ArtifactHistoryError("provenance constraint snapshot hash mismatch")
        if record.artifact_version_id in self.provenance:
            raise ArtifactHistoryError("provenance record is immutable and already exists")
        self.provenance[record.artifact_version_id] = record

    def transition_status(
        self,
        version_id: str,
        target_status: str,
        *,
        required_validation_passed: bool = False,
        quality_score: float | None = None,
    ) -> ArtifactVersion:
        version = self.versions[version_id]
        allowed = _ALLOWED_STATUS_TRANSITIONS[version.status]
        if target_status not in allowed:
            raise ArtifactHistoryError(f"invalid version status transition {version.status}->{target_status}")
        if target_status == "APPROVED" and not required_validation_passed:
            raise ArtifactHistoryError("READY version cannot be APPROVED without required validation")
        updated = replace(version, status=target_status, quality_score=quality_score)  # type: ignore[arg-type]
        if updated.immutable_content_identity != version.immutable_content_identity:
            raise AssertionError("status transition mutated immutable version content identity")
        self.versions[version_id] = updated
        return updated

    def fork_branch(
        self,
        *,
        branch_id: str,
        artifact_id: str,
        name: str,
        from_version_id: str,
        created_by: str,
    ) -> ArtifactBranch:
        source = self.versions.get(from_version_id)
        artifact = self.artifacts.get(artifact_id)
        if source is None or artifact is None or source.artifact_id != artifact_id:
            raise ArtifactHistoryError("fork source must belong to artifact")
        branch = ArtifactBranch(
            id=branch_id,
            organization_id=artifact.organization_id,
            artifact_id=artifact_id,
            name=name,
            base_version_id=from_version_id,
            head_version_id=from_version_id,
            created_by=created_by,
        )
        self.add_branch(branch)
        return branch

    def restore_version(
        self,
        *,
        source_version_id: str,
        branch_id: str,
        new_version_id: str,
        new_version_number: int,
        constraint_snapshot_hash: str,
        created_by_type: str,
        created_by_id: str,
        created_at: datetime,
        lineage_edge_id: str,
    ) -> ArtifactVersion:
        source = self.versions.get(source_version_id)
        branch = self.branches.get(branch_id)
        if source is None or branch is None:
            raise ArtifactHistoryError("restore source/branch missing")
        if source.artifact_id != branch.artifact_id or source.organization_id != branch.organization_id:
            raise ArtifactHistoryError("restore source must belong to branch artifact/tenant")
        restored = ArtifactVersion(
            id=new_version_id,
            organization_id=source.organization_id,
            artifact_id=source.artifact_id,
            branch_id=branch.id,
            parent_version_id=branch.head_version_id,
            schema_version=source.schema_version,
            version_number=new_version_number,
            status="DRAFT",
            content_hash=source.content_hash,
            primary_file_id=source.primary_file_id,
            design_document_version_id=source.design_document_version_id,
            quality_score=None,
            constraint_snapshot_hash=constraint_snapshot_hash,
            created_by_type=created_by_type,  # type: ignore[arg-type]
            created_by_id=created_by_id,
            created_at=created_at,
        )
        self.add_version(restored)
        self.add_edge(
            LineageEdge(
                id=lineage_edge_id,
                organization_id=source.organization_id,
                from_version_id=source.id,
                to_version_id=restored.id,
                type="DERIVED_FROM",
                metadata={"operation": "RESTORE"},
            )
        )
        return restored

    def add_edge(self, edge: LineageEdge) -> None:
        source = self.versions.get(edge.from_version_id)
        target = self.versions.get(edge.to_version_id)
        if source is None or target is None:
            raise ArtifactHistoryError("lineage endpoints must exist")
        if source.organization_id != target.organization_id or edge.organization_id != source.organization_id:
            raise CrossTenantLineageError("cross-tenant lineage is forbidden")
        if edge.id in self.edges:
            raise ArtifactHistoryError(f"lineage edge already exists: {edge.id}")
        if any(
            other.from_version_id == edge.from_version_id
            and other.to_version_id == edge.to_version_id
            and other.type == edge.type
            for other in self.edges.values()
        ):
            raise ArtifactHistoryError("duplicate lineage relation")
        if self._reachable(edge.to_version_id, edge.from_version_id):
            raise LineageCycleError("lineage edge would create a cycle")
        self.edges[edge.id] = edge

    def _reachable(self, start: str, goal: str) -> bool:
        adjacency: dict[str, set[str]] = {}
        for edge in self.edges.values():
            adjacency.setdefault(edge.from_version_id, set()).add(edge.to_version_id)
        pending = [start]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == goal:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(adjacency.get(current, ()))
        return False

    def find_versions_by_content_hash(self, organization_id: str, content_hash: str) -> tuple[ArtifactVersion, ...]:
        return tuple(
            sorted(
                (
                    version
                    for version in self.versions.values()
                    if version.organization_id == organization_id and version.content_hash == content_hash
                ),
                key=lambda item: (item.created_at, item.id),
            )
        )

    def lineage_parents(self, version_id: str) -> tuple[ArtifactVersion, ...]:
        parent_ids = {
            edge.from_version_id
            for edge in self.edges.values()
            if edge.to_version_id == version_id
        }
        return tuple(sorted((self.versions[parent_id] for parent_id in parent_ids), key=lambda item: item.id))

    def validate_integrity(self) -> None:
        for branch in self.branches.values():
            if branch.head_version_id is not None and branch.head_version_id not in self.versions:
                raise ArtifactHistoryError("branch head missing")
        for version in self.versions.values():
            if version.primary_file_id is not None:
                file = self.files.get(version.primary_file_id)
                if file is None or file.artifact_version_id != version.id:
                    raise ArtifactHistoryError("primary file does not belong to version")
