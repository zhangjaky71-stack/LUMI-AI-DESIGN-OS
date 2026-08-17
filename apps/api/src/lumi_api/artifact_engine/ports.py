from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from lumi_api.artifacts.models import (
    Artifact,
    ArtifactBranch,
    ArtifactVersion,
    LineageEdge,
)

from .contracts import (
    ApprovalRecord,
    ArtifactOutboxEvent,
    GcAudit,
    GcMark,
    ProvenanceCompleteness,
    ProvenanceEnvelope,
    StorageObjectMetadata,
)


class ArtifactHeadConflict(RuntimeError):
    pass


class ArtifactNotFound(LookupError):
    pass


class ArtifactStorageViolation(RuntimeError):
    pass


class ArtifactRuntimeRepository(Protocol):
    def get_artifact(self, artifact_id: UUID) -> Artifact: ...
    def get_branch(self, branch_id: UUID) -> ArtifactBranch: ...
    def get_version(self, version_id: UUID) -> ArtifactVersion: ...
    def list_versions(self, artifact_id: UUID) -> tuple[ArtifactVersion, ...]: ...
    def list_lineage(self, version_id: UUID) -> tuple[LineageEdge, ...]: ...
    def list_branches(self, artifact_id: UUID) -> tuple[ArtifactBranch, ...]: ...

    def create_artifact_bundle(
        self,
        artifact: Artifact,
        branch: ArtifactBranch,
        event: ArtifactOutboxEvent,
    ) -> None: ...

    def create_artifact_bundle_with_initial_version(
        self,
        artifact: Artifact,
        branch: ArtifactBranch,
        version: ArtifactVersion,
        lineage: tuple[LineageEdge, ...],
        provenance: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
        events: tuple[ArtifactOutboxEvent, ...],
    ) -> None: ...

    def create_branch(self, branch: ArtifactBranch, event: ArtifactOutboxEvent) -> None: ...

    def append_version(
        self,
        *,
        branch_id: UUID,
        expected_head_version_id: UUID | None,
        version_factory: Any,
        lineage_factory: Any,
        provenance: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
        event_factory: Any,
    ) -> tuple[ArtifactVersion, tuple[LineageEdge, ...]]: ...

    def replace_version_status(
        self,
        version: ArtifactVersion,
        *,
        expected_status: str,
        approval: ApprovalRecord | None,
        event: ArtifactOutboxEvent,
    ) -> None: ...

    def get_provenance_envelope(self, version_id: UUID) -> ProvenanceEnvelope: ...
    def get_provenance_completeness(self, version_id: UUID) -> ProvenanceCompleteness: ...
    def record_gc_marks(self, marks: tuple[GcMark, ...]) -> None: ...
    def pending_gc_marks(self, organization_id: UUID) -> tuple[GcMark, ...]: ...
    def complete_gc_mark(self, mark: GcMark, audit: GcAudit) -> None: ...
    def protected_storage_locations(self, organization_id: UUID) -> frozenset[tuple[str, str]]: ...


class ArtifactStoragePort(Protocol):
    def stat_object(
        self, organization_id: UUID, bucket: str, storage_key: str
    ) -> StorageObjectMetadata | None: ...

    def list_objects(self, organization_id: UUID) -> tuple[StorageObjectMetadata, ...]: ...
    def delete_object(self, organization_id: UUID, bucket: str, storage_key: str) -> None: ...


class DesignDocumentReader(Protocol):
    def load_design_document_version(self, version_id: UUID) -> dict[str, Any]: ...


class DesignSemanticDiffPort(Protocol):
    def compare(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]: ...


class RasterVisualDiffPort(Protocol):
    def compare(
        self, left: StorageObjectMetadata, right: StorageObjectMetadata
    ) -> dict[str, float]: ...
