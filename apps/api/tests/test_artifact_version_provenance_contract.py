# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from lumi_api.artifacts import (
    Artifact,
    ArtifactBranch,
    ArtifactContractError,
    ArtifactFile,
    ArtifactGraphViolation,
    ArtifactImmutabilityViolation,
    ArtifactType,
    ArtifactVersion,
    ArtifactVersionStatus,
    CreatedByType,
    FileRole,
    LineageEdge,
    LineageEdgeType,
    ProvenanceRecord,
    RightsPolicy,
    RightsReviewStatus,
    StoredObject,
    archive_artifact,
    assert_same_version_content,
    build_provenance_manifest,
    confirm_gc_deletions,
    content_hash_index,
    create_version,
    fork_branch,
    inherit_rights,
    manifest_hash_sha256,
    mark_gc_candidates,
    restore_version,
    transition_version_status,
    validate_artifact_graph,
)
from lumi_api.domain.ids import new_uuid7

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
GIT_SHA = "d" * 40
NOW = datetime(2026, 8, 16, 6, 30, tzinfo=UTC)


def rights(
    *,
    commercial: bool | None = True,
    redistribution: bool | None = True,
    training: bool | None = False,
    attribution: bool = False,
    status: RightsReviewStatus = RightsReviewStatus.APPROVED,
    license_type: str = "owned",
) -> RightsPolicy:
    return RightsPolicy(
        source_type="USER_UPLOAD",
        owner_assertion="customer-owned",
        license_type=license_type,
        commercial_use=commercial,
        redistribution=redistribution,
        training_use=training,
        attribution_required=attribution,
        source_reference="asset:source",
        review_status=status,
    )


def provenance(
    *,
    input_versions: tuple[UUID, ...] = (),
    input_assets: tuple[UUID, ...] = (),
    generated: bool = False,
    constraint_hash: str | None = SHA_C,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        generation_id=new_uuid7() if generated else None,
        provider="openai" if generated else None,
        model="image-model" if generated else None,
        provider_request_id="req-1" if generated else None,
        prompt_hash=SHA_B if generated else None,
        prompt_ref="prompt:v1" if generated else None,
        prompt_template_version="poster-v2" if generated else None,
        input_asset_ids=input_assets,
        input_artifact_version_ids=input_versions,
        design_ir_schema_version="lumi.design-ir/1.0",
        constraint_snapshot_hash=constraint_hash,
        recipe_version="recipe-1",
        code_git_sha=GIT_SHA,
    )


def file_ref(
    checksum: str = SHA_A,
    *,
    role: FileRole = FileRole.ORIGINAL,
    storage_key: str = "artifacts/original.png",
) -> ArtifactFile:
    return ArtifactFile(
        id=new_uuid7(),
        role=role,
        bucket="lumi-artifacts",
        storage_key=storage_key,
        mime_type="image/png",
        size_bytes=1024,
        checksum_sha256=checksum,
        width=750,
        height=1624,
    )


def artifact_fixture(
    *, organization_id: UUID | None = None
) -> tuple[Artifact, ArtifactBranch, ArtifactVersion]:
    org = organization_id or new_uuid7()
    artifact = Artifact(
        id=new_uuid7(),
        organization_id=org,
        project_id=new_uuid7(),
        type=ArtifactType.RASTER_IMAGE,
        name="Campaign Poster",
        rights=rights(),
    )
    branch = ArtifactBranch(
        id=new_uuid7(),
        organization_id=org,
        artifact_id=artifact.id,
        name="main",
        created_by_type=CreatedByType.USER,
        created_by_id="user-1",
        created_at=NOW,
    )
    original = file_ref()
    version, branch = create_version(
        branch,
        (),
        version_id=new_uuid7(),
        content_hash=SHA_A,
        files=(original,),
        provenance=provenance(),
        rights=rights(),
        created_by_type=CreatedByType.USER,
        created_by_id="user-1",
        created_at=NOW,
        primary_file_id=original.id,
        constraint_snapshot_hash=SHA_C,
    )
    return artifact, branch, version


def test_canvas_is_not_an_artifact_type() -> None:
    with pytest.raises(ValidationError):
        Artifact.model_validate(
            {
                "id": str(new_uuid7()),
                "organization_id": str(new_uuid7()),
                "project_id": str(new_uuid7()),
                "type": "CANVAS",
                "name": "not durable truth",
                "rights": rights().model_dump(mode="json"),
            }
        )


def test_artifact_file_rejects_signed_or_public_urls() -> None:
    with pytest.raises(ValidationError):
        ArtifactFile(
            id=new_uuid7(),
            role=FileRole.ORIGINAL,
            bucket="bucket",
            storage_key="https://example.com/file?X-Amz-Signature=secret",
            mime_type="image/png",
            size_bytes=1,
            checksum_sha256=SHA_A,
        )


def test_generation_provenance_requires_provider_model_and_prompt_hash() -> None:
    with pytest.raises(ValidationError):
        ProvenanceRecord(
            generation_id=new_uuid7(),
            code_git_sha=GIT_SHA,
        )


def test_constraint_snapshot_must_match_provenance() -> None:
    artifact, branch, _ = artifact_fixture()
    with pytest.raises(ValidationError):
        ArtifactVersion(
            id=new_uuid7(),
            organization_id=artifact.organization_id,
            artifact_id=artifact.id,
            branch_id=branch.id,
            version_number=2,
            content_hash=SHA_A,
            constraint_snapshot_hash=SHA_A,
            created_by_type=CreatedByType.SYSTEM,
            created_at=NOW,
            provenance=provenance(constraint_hash=SHA_B),
            rights=rights(),
        )


def test_version_model_is_frozen() -> None:
    _, _, version = artifact_fixture()
    with pytest.raises(ValidationError):
        version.__setattr__("content_hash", SHA_B)


def test_only_status_may_change_for_same_version_identity() -> None:
    _, _, version = artifact_fixture()
    ready = transition_version_status(version, ArtifactVersionStatus.READY)
    assert ready.id == version.id
    assert ready.content_hash == version.content_hash
    assert ready.status == ArtifactVersionStatus.READY
    assert_same_version_content(version, ready)

    changed = version.model_copy(update={"content_hash": SHA_B})
    with pytest.raises(ArtifactImmutabilityViolation):
        assert_same_version_content(version, changed)


def test_approval_requires_ready_and_validation_pass() -> None:
    _, _, version = artifact_fixture()
    with pytest.raises(ArtifactContractError):
        transition_version_status(version, ArtifactVersionStatus.APPROVED)
    ready = transition_version_status(version, ArtifactVersionStatus.READY)
    with pytest.raises(ArtifactContractError):
        transition_version_status(ready, ArtifactVersionStatus.APPROVED)
    approved = transition_version_status(
        ready,
        ArtifactVersionStatus.APPROVED,
        validation_passed=True,
    )
    assert approved.status == ArtifactVersionStatus.APPROVED
    with pytest.raises(ArtifactContractError):
        transition_version_status(approved, ArtifactVersionStatus.ARCHIVED)


def test_rights_rejected_version_cannot_be_approved() -> None:
    artifact, branch, first = artifact_fixture()
    rejected_rights = rights(status=RightsReviewStatus.REJECTED)
    version, _ = create_version(
        branch,
        (first,),
        version_id=new_uuid7(),
        content_hash=SHA_B,
        files=(file_ref(SHA_B, storage_key="artifacts/v2.png"),),
        provenance=provenance(),
        rights=rejected_rights,
        created_by_type=CreatedByType.USER,
        created_by_id="user-1",
        created_at=NOW + timedelta(minutes=1),
        constraint_snapshot_hash=SHA_C,
    )
    ready = transition_version_status(version, ArtifactVersionStatus.READY)
    with pytest.raises(ArtifactContractError):
        transition_version_status(
            ready,
            ArtifactVersionStatus.APPROVED,
            validation_passed=True,
        )
    assert artifact.id == version.artifact_id


def test_fork_points_to_source_without_rewriting_source() -> None:
    _, _, version = artifact_fixture()
    fork = fork_branch(
        version,
        branch_id=new_uuid7(),
        name="alt-dark",
        created_by_type=CreatedByType.USER,
        created_by_id="user-2",
        created_at=NOW + timedelta(minutes=1),
    )
    assert fork.base_version_id == version.id
    assert fork.head_version_id == version.id
    assert version.version_number == 1


def test_restore_creates_new_version_and_lineage_edge() -> None:
    artifact, branch, version1 = artifact_fixture()
    file2 = file_ref(SHA_B, storage_key="artifacts/v2.png")
    version2, branch = create_version(
        branch,
        (version1,),
        version_id=new_uuid7(),
        content_hash=SHA_B,
        files=(file2,),
        provenance=provenance(),
        rights=rights(),
        created_by_type=CreatedByType.USER,
        created_by_id="user-1",
        created_at=NOW + timedelta(minutes=1),
        primary_file_id=file2.id,
        constraint_snapshot_hash=SHA_C,
    )
    restored, branch, edge = restore_version(
        version1,
        branch,
        (version1, version2),
        version_id=new_uuid7(),
        provenance=provenance(input_versions=(version1.id,)),
        created_by_type=CreatedByType.USER,
        created_by_id="user-1",
        created_at=NOW + timedelta(minutes=2),
    )
    assert restored.id not in {version1.id, version2.id}
    assert restored.version_number == 3
    assert restored.content_hash == version1.content_hash
    assert branch.head_version_id == restored.id
    assert edge.artifact_version_id == restored.id
    assert edge.source_artifact_version_id == version1.id
    assert edge.type == LineageEdgeType.DERIVED_FROM
    assert artifact.id == restored.artifact_id


def test_restore_rejects_cross_organization() -> None:
    _, branch, _ = artifact_fixture(organization_id=new_uuid7())
    _, _, foreign_version = artifact_fixture(organization_id=new_uuid7())
    with pytest.raises(ArtifactGraphViolation):
        restore_version(
            foreign_version,
            branch,
            (),
            version_id=new_uuid7(),
            provenance=provenance(input_versions=(foreign_version.id,)),
            created_by_type=CreatedByType.SYSTEM,
            created_by_id=None,
            created_at=NOW,
        )


def test_lineage_supports_multi_parent_same_tenant() -> None:
    artifact, branch, version1 = artifact_fixture()
    file2 = file_ref(SHA_B, storage_key="artifacts/source2.png")
    version2, branch = create_version(
        branch,
        (version1,),
        version_id=new_uuid7(),
        content_hash=SHA_B,
        files=(file2,),
        provenance=provenance(),
        rights=rights(),
        created_by_type=CreatedByType.SYSTEM,
        created_by_id=None,
        created_at=NOW + timedelta(minutes=1),
        constraint_snapshot_hash=SHA_C,
    )
    file3 = file_ref(SHA_C, storage_key="artifacts/composite.png")
    version3, branch = create_version(
        branch,
        (version1, version2),
        version_id=new_uuid7(),
        content_hash=SHA_C,
        files=(file3,),
        provenance=provenance(input_versions=(version1.id, version2.id)),
        rights=rights(),
        created_by_type=CreatedByType.AGENT,
        created_by_id="agent-composer",
        created_at=NOW + timedelta(minutes=2),
        constraint_snapshot_hash=SHA_C,
    )
    edges = (
        LineageEdge(
            id=new_uuid7(),
            organization_id=artifact.organization_id,
            artifact_version_id=version3.id,
            source_artifact_version_id=version1.id,
            type=LineageEdgeType.COMPOSED_FROM,
            created_at=NOW,
        ),
        LineageEdge(
            id=new_uuid7(),
            organization_id=artifact.organization_id,
            artifact_version_id=version3.id,
            source_artifact_version_id=version2.id,
            type=LineageEdgeType.COMPOSED_FROM,
            created_at=NOW,
        ),
    )
    validate_artifact_graph(
        (artifact,),
        (branch,),
        (version1, version2, version3),
        edges,
    )


def test_cross_tenant_lineage_is_rejected() -> None:
    artifact1, branch1, version1 = artifact_fixture(organization_id=new_uuid7())
    artifact2, branch2, version2 = artifact_fixture(organization_id=new_uuid7())
    edge = LineageEdge(
        id=new_uuid7(),
        organization_id=artifact1.organization_id,
        artifact_version_id=version1.id,
        source_artifact_version_id=version2.id,
        type=LineageEdgeType.REFERENCE_USED,
        created_at=NOW,
    )
    with pytest.raises(ArtifactGraphViolation):
        validate_artifact_graph(
            (artifact1, artifact2),
            (branch1, branch2),
            (version1, version2),
            (edge,),
        )


def test_lineage_cycle_is_rejected() -> None:
    artifact, branch, version1 = artifact_fixture()
    version2, branch = create_version(
        branch,
        (version1,),
        version_id=new_uuid7(),
        content_hash=SHA_B,
        files=(file_ref(SHA_B, storage_key="artifacts/v2.png"),),
        provenance=provenance(),
        rights=rights(),
        created_by_type=CreatedByType.SYSTEM,
        created_by_id=None,
        created_at=NOW + timedelta(minutes=1),
        constraint_snapshot_hash=SHA_C,
    )
    edges = (
        LineageEdge(
            id=new_uuid7(),
            organization_id=artifact.organization_id,
            artifact_version_id=version2.id,
            source_artifact_version_id=version1.id,
            type=LineageEdgeType.EDITED_FROM,
            created_at=NOW,
        ),
        LineageEdge(
            id=new_uuid7(),
            organization_id=artifact.organization_id,
            artifact_version_id=version1.id,
            source_artifact_version_id=version2.id,
            type=LineageEdgeType.DERIVED_FROM,
            created_at=NOW,
        ),
    )
    with pytest.raises(ArtifactGraphViolation):
        validate_artifact_graph(
            (artifact,),
            (branch,),
            (version1, version2),
            edges,
        )


def test_content_hash_index_detects_deduplicated_content() -> None:
    _, branch, version1 = artifact_fixture()
    version2, _ = create_version(
        branch,
        (version1,),
        version_id=new_uuid7(),
        content_hash=version1.content_hash,
        files=(file_ref(SHA_A, storage_key="artifacts/copy.png"),),
        provenance=provenance(),
        rights=rights(),
        created_by_type=CreatedByType.SYSTEM,
        created_by_id=None,
        created_at=NOW + timedelta(minutes=1),
        constraint_snapshot_hash=SHA_C,
    )
    index = content_hash_index((version1, version2))
    assert set(index[SHA_A]) == {version1.id, version2.id}


def test_rights_inheritance_is_conservative() -> None:
    owned = rights(commercial=True, redistribution=True, attribution=False)
    restricted = rights(
        commercial=False,
        redistribution=None,
        attribution=True,
        status=RightsReviewStatus.PENDING,
        license_type="third-party",
    )
    inherited = inherit_rights((owned, restricted))
    assert inherited.commercial_use is False
    assert inherited.redistribution is None
    assert inherited.attribution_required is True
    assert inherited.license_type == "MIXED"
    assert inherited.review_status == RightsReviewStatus.PENDING


def test_export_manifest_contains_traceability_but_not_prompt_content() -> None:
    artifact, branch, source = artifact_fixture()
    generated_file = file_ref(SHA_B, storage_key="artifacts/generated.png")
    generated, branch = create_version(
        branch,
        (source,),
        version_id=new_uuid7(),
        content_hash=SHA_B,
        files=(generated_file,),
        provenance=provenance(
            input_versions=(source.id,),
            input_assets=(new_uuid7(),),
            generated=True,
        ),
        rights=rights(),
        created_by_type=CreatedByType.AGENT,
        created_by_id="agent-1",
        created_at=NOW + timedelta(minutes=1),
        primary_file_id=generated_file.id,
        constraint_snapshot_hash=SHA_C,
    )
    edge = LineageEdge(
        id=new_uuid7(),
        organization_id=artifact.organization_id,
        artifact_version_id=generated.id,
        source_artifact_version_id=source.id,
        type=LineageEdgeType.GENERATED_FROM,
        created_at=NOW,
    )
    manifest = build_provenance_manifest(
        generated,
        (source, generated),
        (edge,),
        created_at=NOW,
    )
    dumped = manifest.model_dump_json()
    assert source.id in manifest.source_artifact_version_ids
    assert ("openai", "image-model") in manifest.models
    assert SHA_A in manifest.checksums and SHA_B in manifest.checksums
    assert "prompt:v1" not in dumped
    assert "provider_request_id" not in dumped
    assert len(manifest_hash_sha256(manifest)) == 64
    assert branch.head_version_id == generated.id


def test_artifact_archive_preserves_retention_and_legal_hold() -> None:
    artifact, _, _ = artifact_fixture()
    held = artifact.model_copy(update={"legal_hold": True})
    archived = archive_artifact(
        held,
        archived_at=NOW,
        retention_until=NOW + timedelta(days=30),
    )
    assert archived.archived_at == NOW
    assert archived.retention_until == NOW + timedelta(days=30)
    assert archived.legal_hold is True


def test_gc_mark_and_sweep_never_deletes_live_retained_or_held_objects() -> None:
    org = new_uuid7()
    live = StoredObject(
        organization_id=org,
        bucket="b",
        storage_key="live.png",
        checksum_sha256=SHA_A,
    )
    retained = StoredObject(
        organization_id=org,
        bucket="b",
        storage_key="retained.png",
        checksum_sha256=SHA_B,
    )
    held = StoredObject(
        organization_id=org,
        bucket="b",
        storage_key="held.png",
        checksum_sha256=SHA_C,
    )
    orphan = StoredObject(
        organization_id=org,
        bucket="b",
        storage_key="orphan.png",
        checksum_sha256="e" * 64,
    )
    candidates = mark_gc_candidates(
        (live, retained, held, orphan),
        live_references=frozenset({live.location}),
        retention_references=frozenset({retained.location}),
        legal_hold_references=frozenset({held.location}),
        marked_at=NOW,
        delay=timedelta(days=7),
    )
    assert [item.location for item in candidates] == [orphan.location]
    assert not confirm_gc_deletions(
        candidates,
        live_references=frozenset(),
        retention_references=frozenset(),
        legal_hold_references=frozenset(),
        checked_at=NOW + timedelta(days=6),
    )
    assert confirm_gc_deletions(
        candidates,
        live_references=frozenset(),
        retention_references=frozenset(),
        legal_hold_references=frozenset(),
        checked_at=NOW + timedelta(days=8),
    ) == candidates


def test_gc_second_check_protects_object_that_became_live_again() -> None:
    orphan = StoredObject(
        organization_id=new_uuid7(),
        bucket="b",
        storage_key="orphan.png",
        checksum_sha256=SHA_A,
    )
    candidates = mark_gc_candidates(
        (orphan,),
        live_references=frozenset(),
        retention_references=frozenset(),
        legal_hold_references=frozenset(),
        marked_at=NOW,
        delay=timedelta(days=1),
    )
    safe = confirm_gc_deletions(
        candidates,
        live_references=frozenset({orphan.location}),
        retention_references=frozenset(),
        legal_hold_references=frozenset(),
        checked_at=NOW + timedelta(days=2),
    )
    assert safe == ()
