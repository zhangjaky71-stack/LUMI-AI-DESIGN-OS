from __future__ import annotations

from datetime import datetime
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .models import (
    Artifact,
    ArtifactBranch,
    ArtifactFile,
    ArtifactVersion,
    ArtifactVersionStatus,
    CreatedByType,
    LineageEdge,
    LineageEdgeType,
    ProvenanceRecord,
    RightsPolicy,
    RightsReviewStatus,
)


class ArtifactContractError(ValueError):
    pass


class ArtifactImmutabilityViolation(ArtifactContractError):
    pass


class ArtifactGraphViolation(ArtifactContractError):
    pass


_ALLOWED_STATUS_TRANSITIONS: dict[
    ArtifactVersionStatus, frozenset[ArtifactVersionStatus]
] = {
    ArtifactVersionStatus.DRAFT: frozenset(
        {
            ArtifactVersionStatus.READY,
            ArtifactVersionStatus.REJECTED,
            ArtifactVersionStatus.ARCHIVED,
        }
    ),
    ArtifactVersionStatus.READY: frozenset(
        {
            ArtifactVersionStatus.APPROVED,
            ArtifactVersionStatus.REJECTED,
            ArtifactVersionStatus.ARCHIVED,
        }
    ),
    ArtifactVersionStatus.APPROVED: frozenset(),
    ArtifactVersionStatus.REJECTED: frozenset({ArtifactVersionStatus.ARCHIVED}),
    ArtifactVersionStatus.ARCHIVED: frozenset(),
}

_CONTENT_FIELDS = (
    "organization_id",
    "artifact_id",
    "branch_id",
    "parent_version_id",
    "version_number",
    "content_hash",
    "primary_file_id",
    "design_document_version_id",
    "quality_score",
    "constraint_snapshot_hash",
    "created_by_type",
    "created_by_id",
    "created_at",
    "files",
    "provenance",
    "rights",
)


def assert_same_version_content(before: ArtifactVersion, after: ArtifactVersion) -> None:
    if before.id != after.id:
        raise ArtifactImmutabilityViolation("version identity changed")
    changed = [
        field_name
        for field_name in _CONTENT_FIELDS
        if getattr(before, field_name) != getattr(after, field_name)
    ]
    if changed:
        raise ArtifactImmutabilityViolation(
            "artifact version content/provenance is immutable: " + ",".join(changed)
        )


def transition_version_status(
    version: ArtifactVersion,
    target: ArtifactVersionStatus,
    *,
    validation_passed: bool = False,
) -> ArtifactVersion:
    if target not in _ALLOWED_STATUS_TRANSITIONS[version.status]:
        raise ArtifactContractError(
            f"invalid artifact version status transition: {version.status} -> {target}"
        )
    if target == ArtifactVersionStatus.APPROVED:
        if version.status != ArtifactVersionStatus.READY:
            raise ArtifactContractError("only READY versions can be approved")
        if not validation_passed:
            raise ArtifactContractError("approval requires validation_passed=true")
        if version.rights.review_status == RightsReviewStatus.REJECTED:
            raise ArtifactContractError("rights-rejected version cannot be approved")
    updated = version.model_copy(update={"status": target})
    assert_same_version_content(version, updated)
    return updated


def archive_artifact(
    artifact: Artifact,
    *,
    archived_at: datetime,
    retention_until: datetime,
) -> Artifact:
    if archived_at.tzinfo is None or archived_at.utcoffset() is None:
        raise ArtifactContractError("archived_at must be timezone-aware")
    if retention_until.tzinfo is None or retention_until.utcoffset() is None:
        raise ArtifactContractError("retention_until must be timezone-aware")
    if retention_until < archived_at:
        raise ArtifactContractError("retention_until cannot precede archived_at")
    if artifact.archived_at is not None:
        raise ArtifactContractError("artifact is already archived")
    return artifact.model_copy(
        update={"archived_at": archived_at, "retention_until": retention_until}
    )


def fork_branch(
    source_version: ArtifactVersion,
    *,
    branch_id: UUID,
    name: str,
    created_by_type: CreatedByType,
    created_by_id: str | None,
    created_at: datetime,
) -> ArtifactBranch:
    return ArtifactBranch(
        id=branch_id,
        organization_id=source_version.organization_id,
        artifact_id=source_version.artifact_id,
        name=name,
        base_version_id=source_version.id,
        head_version_id=source_version.id,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        created_at=created_at,
    )


def next_branch_version_number(
    branch_id: UUID,
    versions: tuple[ArtifactVersion, ...],
) -> int:
    numbers = [item.version_number for item in versions if item.branch_id == branch_id]
    return max(numbers, default=0) + 1


def create_version(
    branch: ArtifactBranch,
    existing_versions: tuple[ArtifactVersion, ...],
    *,
    version_id: UUID,
    content_hash: str,
    files: tuple[ArtifactFile, ...],
    provenance: ProvenanceRecord,
    rights: RightsPolicy,
    created_by_type: CreatedByType,
    created_by_id: str | None,
    created_at: datetime,
    primary_file_id: UUID | None = None,
    design_document_version_id: UUID | None = None,
    quality_score: float | None = None,
    constraint_snapshot_hash: str | None = None,
) -> tuple[ArtifactVersion, ArtifactBranch]:
    if any(item.id == version_id for item in existing_versions):
        raise ArtifactContractError("version_id already exists")
    version_number = next_branch_version_number(branch.id, existing_versions)
    version = ArtifactVersion(
        id=version_id,
        organization_id=branch.organization_id,
        artifact_id=branch.artifact_id,
        branch_id=branch.id,
        parent_version_id=branch.head_version_id,
        version_number=version_number,
        content_hash=content_hash,
        primary_file_id=primary_file_id,
        design_document_version_id=design_document_version_id,
        quality_score=quality_score,
        constraint_snapshot_hash=constraint_snapshot_hash,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        created_at=created_at,
        files=files,
        provenance=provenance,
        rights=rights,
    )
    updated_branch = branch.model_copy(update={"head_version_id": version.id})
    return version, updated_branch


def restore_version(
    source_version: ArtifactVersion,
    target_branch: ArtifactBranch,
    existing_versions: tuple[ArtifactVersion, ...],
    *,
    version_id: UUID,
    provenance: ProvenanceRecord,
    created_by_type: CreatedByType,
    created_by_id: str | None,
    created_at: datetime,
) -> tuple[ArtifactVersion, ArtifactBranch, LineageEdge]:
    if source_version.organization_id != target_branch.organization_id:
        raise ArtifactGraphViolation("restore cannot cross organizations")
    if source_version.artifact_id != target_branch.artifact_id:
        raise ArtifactGraphViolation("restore source must belong to the same artifact")
    if source_version.id not in provenance.input_artifact_version_ids:
        raise ArtifactContractError(
            "restore provenance must reference the restored source version"
        )
    restored, updated_branch = create_version(
        target_branch,
        existing_versions,
        version_id=version_id,
        content_hash=source_version.content_hash,
        files=source_version.files,
        provenance=provenance,
        rights=source_version.rights,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        created_at=created_at,
        primary_file_id=source_version.primary_file_id,
        design_document_version_id=source_version.design_document_version_id,
        quality_score=source_version.quality_score,
        constraint_snapshot_hash=source_version.constraint_snapshot_hash,
    )
    edge = LineageEdge(
        id=new_uuid7(),
        organization_id=source_version.organization_id,
        artifact_version_id=restored.id,
        source_artifact_version_id=source_version.id,
        type=LineageEdgeType.DERIVED_FROM,
        created_at=created_at,
        metadata=(("operation", "restore"),),
    )
    return restored, updated_branch, edge


def content_hash_index(
    versions: tuple[ArtifactVersion, ...],
) -> dict[str, tuple[UUID, ...]]:
    buckets: dict[str, list[UUID]] = {}
    for version in versions:
        buckets.setdefault(version.content_hash, []).append(version.id)
    return {
        content_hash: tuple(sorted(version_ids, key=str))
        for content_hash, version_ids in sorted(buckets.items())
    }


def inherit_rights(sources: tuple[RightsPolicy, ...]) -> RightsPolicy:
    if not sources:
        raise ArtifactContractError("rights inheritance requires at least one source")

    def conservative_flag(field_name: str) -> bool | None:
        values = [getattr(item, field_name) for item in sources]
        if any(value is False for value in values):
            return False
        if any(value is None for value in values):
            return None
        return True

    source_types = sorted({item.source_type for item in sources})
    owners = sorted({item.owner_assertion for item in sources})
    licenses = sorted({item.license_type for item in sources})
    source_refs = sorted(
        {item.source_reference for item in sources if item.source_reference is not None}
    )
    if any(item.review_status == RightsReviewStatus.REJECTED for item in sources):
        review_status = RightsReviewStatus.REJECTED
    elif all(item.review_status == RightsReviewStatus.APPROVED for item in sources):
        review_status = RightsReviewStatus.APPROVED
    elif any(item.review_status == RightsReviewStatus.PENDING for item in sources):
        review_status = RightsReviewStatus.PENDING
    else:
        review_status = RightsReviewStatus.UNREVIEWED

    return RightsPolicy(
        source_type=source_types[0] if len(source_types) == 1 else "MIXED",
        owner_assertion=owners[0] if len(owners) == 1 else "MIXED",
        license_type=licenses[0] if len(licenses) == 1 else "MIXED",
        commercial_use=conservative_flag("commercial_use"),
        redistribution=conservative_flag("redistribution"),
        training_use=conservative_flag("training_use"),
        attribution_required=any(item.attribution_required for item in sources),
        source_reference=" | ".join(source_refs) if source_refs else None,
        review_status=review_status,
    )


def validate_artifact_graph(
    artifacts: tuple[Artifact, ...],
    branches: tuple[ArtifactBranch, ...],
    versions: tuple[ArtifactVersion, ...],
    edges: tuple[LineageEdge, ...],
) -> None:
    artifact_by_id = {item.id: item for item in artifacts}
    branch_by_id = {item.id: item for item in branches}
    version_by_id = {item.id: item for item in versions}
    if len(artifact_by_id) != len(artifacts):
        raise ArtifactGraphViolation("duplicate artifact id")
    if len(branch_by_id) != len(branches):
        raise ArtifactGraphViolation("duplicate branch id")
    if len(version_by_id) != len(versions):
        raise ArtifactGraphViolation("duplicate artifact version id")

    branch_names: set[tuple[UUID, str]] = set()
    for branch in branches:
        artifact = artifact_by_id.get(branch.artifact_id)
        if artifact is None:
            raise ArtifactGraphViolation("branch references missing artifact")
        if artifact.organization_id != branch.organization_id:
            raise ArtifactGraphViolation("branch crosses organization boundary")
        key = (branch.artifact_id, branch.name)
        if key in branch_names:
            raise ArtifactGraphViolation("branch name must be unique per artifact")
        branch_names.add(key)
        for ref_name, ref_id in (
            ("base", branch.base_version_id),
            ("head", branch.head_version_id),
        ):
            if ref_id is None:
                continue
            ref = version_by_id.get(ref_id)
            if ref is None:
                raise ArtifactGraphViolation(f"branch {ref_name} references missing version")
            if ref.organization_id != branch.organization_id:
                raise ArtifactGraphViolation(f"branch {ref_name} crosses organization boundary")
            if ref.artifact_id != branch.artifact_id:
                raise ArtifactGraphViolation(f"branch {ref_name} references another artifact")

    version_numbers: set[tuple[UUID, int]] = set()
    for version in versions:
        artifact = artifact_by_id.get(version.artifact_id)
        branch = branch_by_id.get(version.branch_id)
        if artifact is None or branch is None:
            raise ArtifactGraphViolation("version references missing artifact/branch")
        if version.organization_id != artifact.organization_id:
            raise ArtifactGraphViolation("version crosses artifact organization boundary")
        if branch.organization_id != version.organization_id:
            raise ArtifactGraphViolation("version crosses branch organization boundary")
        if branch.artifact_id != version.artifact_id:
            raise ArtifactGraphViolation("version branch belongs to another artifact")
        key = (version.branch_id, version.version_number)
        if key in version_numbers:
            raise ArtifactGraphViolation("version_number must be unique within a branch")
        version_numbers.add(key)
        if version.parent_version_id is not None:
            parent = version_by_id.get(version.parent_version_id)
            if parent is None:
                raise ArtifactGraphViolation("parent_version_id references missing version")
            if parent.organization_id != version.organization_id:
                raise ArtifactGraphViolation("parent_version_id crosses organization boundary")
            if parent.artifact_id != version.artifact_id:
                raise ArtifactGraphViolation("parent_version_id references another artifact")

    edge_keys: set[tuple[UUID, UUID, LineageEdgeType]] = set()
    adjacency: dict[UUID, set[UUID]] = {version_id: set() for version_id in version_by_id}
    for edge in edges:
        result = version_by_id.get(edge.artifact_version_id)
        source = version_by_id.get(edge.source_artifact_version_id)
        if result is None or source is None:
            raise ArtifactGraphViolation("lineage edge references missing version")
        if result.organization_id != edge.organization_id or source.organization_id != edge.organization_id:
            raise ArtifactGraphViolation("lineage edge crosses organization boundary")
        key = (edge.artifact_version_id, edge.source_artifact_version_id, edge.type)
        if key in edge_keys:
            raise ArtifactGraphViolation("duplicate lineage edge")
        edge_keys.add(key)
        adjacency[edge.artifact_version_id].add(edge.source_artifact_version_id)

    visited: set[UUID] = set()
    active: set[UUID] = set()

    def visit(version_id: UUID) -> None:
        if version_id in active:
            raise ArtifactGraphViolation("lineage graph contains a cycle")
        if version_id in visited:
            return
        active.add(version_id)
        for source_id in adjacency[version_id]:
            visit(source_id)
        active.remove(version_id)
        visited.add(version_id)

    for version_id in adjacency:
        visit(version_id)
