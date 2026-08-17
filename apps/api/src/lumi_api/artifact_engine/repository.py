from __future__ import annotations

from threading import RLock
from uuid import UUID

from lumi_api.artifacts.engine import ArtifactGraphViolation, validate_artifact_graph
from lumi_api.artifacts.models import Artifact, ArtifactBranch, ArtifactVersion, LineageEdge

from .contracts import (
    ApprovalRecord,
    ArtifactOutboxEvent,
    GcAudit,
    GcMark,
    ProvenanceCompleteness,
    ProvenanceEnvelope,
)
from .ports import ArtifactHeadConflict, ArtifactNotFound


class InMemoryArtifactRepository:
    """Deterministic transaction twin for Artifact Engine contract tests.

    Production code can implement ArtifactRuntimeRepository against PostgreSQL while
    keeping the same compare-and-swap branch-head semantics.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self.artifacts: dict[UUID, Artifact] = {}
        self.branches: dict[UUID, ArtifactBranch] = {}
        self.versions: dict[UUID, ArtifactVersion] = {}
        self.lineage: dict[UUID, LineageEdge] = {}
        self.provenance: dict[UUID, ProvenanceEnvelope] = {}
        self.completeness: dict[UUID, ProvenanceCompleteness] = {}
        self.approvals: dict[UUID, ApprovalRecord] = {}
        self.outbox: list[ArtifactOutboxEvent] = []
        self.gc_marks: dict[UUID, GcMark] = {}
        self.gc_audits: list[GcAudit] = []

    def get_artifact(self, artifact_id: UUID) -> Artifact:
        try:
            return self.artifacts[artifact_id]
        except KeyError as exc:
            raise ArtifactNotFound(f"artifact {artifact_id} not found") from exc

    def get_branch(self, branch_id: UUID) -> ArtifactBranch:
        try:
            return self.branches[branch_id]
        except KeyError as exc:
            raise ArtifactNotFound(f"branch {branch_id} not found") from exc

    def get_version(self, version_id: UUID) -> ArtifactVersion:
        try:
            return self.versions[version_id]
        except KeyError as exc:
            raise ArtifactNotFound(f"version {version_id} not found") from exc

    def list_versions(self, artifact_id: UUID) -> tuple[ArtifactVersion, ...]:
        values = [
            item for item in self.versions.values() if item.artifact_id == artifact_id
        ]
        return tuple(
            sorted(values, key=lambda item: (str(item.branch_id), item.version_number))
        )

    def list_lineage(self, version_id: UUID) -> tuple[LineageEdge, ...]:
        values = [
            item for item in self.lineage.values()
            if item.artifact_version_id == version_id
        ]
        return tuple(
            sorted(
                values,
                key=lambda item: (item.type.value, str(item.source_artifact_version_id)),
            )
        )

    def list_branches(self, artifact_id: UUID) -> tuple[ArtifactBranch, ...]:
        values = [item for item in self.branches.values() if item.artifact_id == artifact_id]
        return tuple(sorted(values, key=lambda item: item.name))

    def create_artifact_bundle(
        self,
        artifact: Artifact,
        branch: ArtifactBranch,
        event: ArtifactOutboxEvent,
    ) -> None:
        with self._lock:
            if artifact.id in self.artifacts:
                raise ArtifactGraphViolation("artifact already exists")
            if branch.id in self.branches:
                raise ArtifactGraphViolation("branch already exists")
            self.artifacts[artifact.id] = artifact
            self.branches[branch.id] = branch
            try:
                self._validate_graph()
            except Exception:
                self.artifacts.pop(artifact.id, None)
                self.branches.pop(branch.id, None)
                raise
            self.outbox.append(event)

    def create_artifact_bundle_with_initial_version(
        self,
        artifact: Artifact,
        branch: ArtifactBranch,
        version: ArtifactVersion,
        lineage: tuple[LineageEdge, ...],
        provenance: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
        events: tuple[ArtifactOutboxEvent, ...],
    ) -> None:
        with self._lock:
            if (
                artifact.id in self.artifacts
                or branch.id in self.branches
                or version.id in self.versions
            ):
                raise ArtifactGraphViolation("artifact bundle already exists")
            if version.artifact_id != artifact.id or version.branch_id != branch.id:
                raise ArtifactGraphViolation(
                    "initial version must belong to the created artifact/main branch"
                )
            if any(edge.id in self.lineage for edge in lineage):
                raise ArtifactGraphViolation("lineage edge already exists")
            committed_branch = branch.model_copy(
                update={"base_version_id": version.id, "head_version_id": version.id}
            )
            self.artifacts[artifact.id] = artifact
            self.branches[branch.id] = committed_branch
            self.versions[version.id] = version
            for edge in lineage:
                self.lineage[edge.id] = edge
            self.provenance[version.id] = provenance
            self.completeness[version.id] = completeness
            try:
                self._validate_graph()
            except Exception:
                self.artifacts.pop(artifact.id, None)
                self.branches.pop(branch.id, None)
                self.versions.pop(version.id, None)
                self.provenance.pop(version.id, None)
                self.completeness.pop(version.id, None)
                for edge in lineage:
                    self.lineage.pop(edge.id, None)
                raise
            self.outbox.extend(events)

    def create_branch(self, branch: ArtifactBranch, event: ArtifactOutboxEvent) -> None:
        with self._lock:
            if branch.id in self.branches:
                raise ArtifactGraphViolation("branch already exists")
            if any(
                item.artifact_id == branch.artifact_id and item.name == branch.name
                for item in self.branches.values()
            ):
                raise ArtifactGraphViolation("branch name must be unique per artifact")
            self.branches[branch.id] = branch
            try:
                self._validate_graph()
            except Exception:
                self.branches.pop(branch.id, None)
                raise
            self.outbox.append(event)

    def append_version(
        self,
        *,
        branch_id: UUID,
        expected_head_version_id: UUID | None,
        version_factory,
        lineage_factory,
        provenance: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
        event_factory,
    ) -> tuple[ArtifactVersion, tuple[LineageEdge, ...]]:
        with self._lock:
            branch = self.get_branch(branch_id)
            if branch.head_version_id != expected_head_version_id:
                raise ArtifactHeadConflict(
                    "branch head changed: "
                    f"expected={expected_head_version_id} actual={branch.head_version_id}"
                )
            next_number = max(
                (
                    item.version_number
                    for item in self.versions.values()
                    if item.branch_id == branch_id
                ),
                default=0,
            ) + 1
            version = version_factory(branch, next_number)
            if version.id in self.versions:
                raise ArtifactGraphViolation("version already exists")
            edges = tuple(lineage_factory(version))
            if any(edge.id in self.lineage for edge in edges):
                raise ArtifactGraphViolation("lineage edge already exists")

            updated_branch = branch.model_copy(update={"head_version_id": version.id})
            self.versions[version.id] = version
            self.branches[branch.id] = updated_branch
            for edge in edges:
                self.lineage[edge.id] = edge
            self.provenance[version.id] = provenance
            self.completeness[version.id] = completeness
            try:
                self._validate_graph()
            except Exception:
                self.versions.pop(version.id, None)
                self.branches[branch.id] = branch
                self.provenance.pop(version.id, None)
                self.completeness.pop(version.id, None)
                for edge in edges:
                    self.lineage.pop(edge.id, None)
                raise
            self.outbox.append(event_factory(version))
            return version, edges

    def replace_version_status(
        self,
        version: ArtifactVersion,
        *,
        expected_status: str,
        approval: ApprovalRecord | None,
        event: ArtifactOutboxEvent,
    ) -> None:
        with self._lock:
            current = self.get_version(version.id)
            if current.status.value != expected_status:
                raise ArtifactHeadConflict(
                    "version status changed: "
                    f"expected={expected_status} actual={current.status.value}"
                )
            self.versions[version.id] = version
            if approval is not None:
                self.approvals[approval.id] = approval
            self.outbox.append(event)

    def get_provenance_envelope(self, version_id: UUID) -> ProvenanceEnvelope:
        try:
            return self.provenance[version_id]
        except KeyError as exc:
            raise ArtifactNotFound(f"provenance for {version_id} not found") from exc

    def get_provenance_completeness(self, version_id: UUID) -> ProvenanceCompleteness:
        try:
            return self.completeness[version_id]
        except KeyError as exc:
            raise ArtifactNotFound(f"provenance completeness for {version_id} not found") from exc

    def record_gc_marks(self, marks: tuple[GcMark, ...]) -> None:
        with self._lock:
            for mark in marks:
                self.gc_marks[mark.id] = mark

    def pending_gc_marks(self, organization_id: UUID) -> tuple[GcMark, ...]:
        values = [
            item
            for item in self.gc_marks.values()
            if item.organization_id == organization_id and item.state.value == "MARKED"
        ]
        return tuple(
            sorted(values, key=lambda item: (item.not_before, item.bucket, item.storage_key))
        )

    def complete_gc_mark(self, mark: GcMark, audit: GcAudit) -> None:
        with self._lock:
            self.gc_marks[mark.id] = mark
            self.gc_audits.append(audit)

    def protected_storage_locations(self, organization_id: UUID) -> frozenset[tuple[str, str]]:
        protected: set[tuple[str, str]] = set()
        for version in self.versions.values():
            if version.organization_id != organization_id:
                continue
            for item in version.files:
                protected.add((item.bucket, item.storage_key))
        return frozenset(protected)

    def _validate_graph(self) -> None:
        validate_artifact_graph(
            tuple(self.artifacts.values()),
            tuple(self.branches.values()),
            tuple(self.versions.values()),
            tuple(self.lineage.values()),
        )
