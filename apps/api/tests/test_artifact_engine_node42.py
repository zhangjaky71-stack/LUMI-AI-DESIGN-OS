from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread
from uuid import UUID

import pytest

from lumi_api.artifact_engine import (
    ArtifactCreateCommand,
    ArtifactEngineService,
    ArtifactHeadConflict,
    ArtifactStorageViolation,
    InMemoryArtifactRepository,
    InitialVersionCreateCommand,
    ProvenanceEnvelope,
    StorageObjectMetadata,
    VersionCreateCommand,
)
from lumi_api.artifacts.engine import ArtifactContractError
from lumi_api.artifacts.models import (
    ArtifactFile,
    ArtifactType,
    CreatedByType,
    FileRole,
    LineageEdgeType,
    ProvenanceRecord,
    RightsPolicy,
)
from lumi_api.domain.ids import new_uuid7

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
SHA = "1" * 64
GIT = "a" * 40


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[UUID, str, str], StorageObjectMetadata] = {}
        self.deleted: list[tuple[UUID, str, str]] = []

    def add(self, org: UUID, bucket: str, key: str, *, checksum: str = SHA) -> None:
        self.objects[(org, bucket, key)] = StorageObjectMetadata(
            organization_id=org,
            bucket=bucket,
            storage_key=key,
            checksum_sha256=checksum,
            size_bytes=10,
            mime_type="image/png",
        )

    def stat_object(self, organization_id: UUID, bucket: str, storage_key: str):
        return self.objects.get((organization_id, bucket, storage_key))

    def list_objects(self, organization_id: UUID):
        return tuple(
            value for (org, _, _), value in self.objects.items() if org == organization_id
        )

    def delete_object(self, organization_id: UUID, bucket: str, storage_key: str) -> None:
        self.deleted.append((organization_id, bucket, storage_key))
        self.objects.pop((organization_id, bucket, storage_key), None)


def rights() -> RightsPolicy:
    return RightsPolicy(
        source_type="user-upload",
        owner_assertion="owned by tenant",
        license_type="owned",
        commercial_use=True,
    )


def provenance(*inputs: UUID, compiler: str = "1.0.0") -> ProvenanceEnvelope:
    return ProvenanceEnvelope(
        record=ProvenanceRecord(
            input_artifact_version_ids=inputs,
            constraint_snapshot_hash="2" * 64,
            code_git_sha=GIT,
        ),
        compiler_version=compiler,
    )


def artifact_file(org: UUID, key: str) -> ArtifactFile:
    return ArtifactFile(
        id=new_uuid7(),
        role=FileRole.ORIGINAL,
        bucket=f"org-{org}",
        storage_key=key,
        mime_type="image/png",
        size_bytes=10,
        checksum_sha256=SHA,
        width=100,
        height=100,
    )


def service_pair():
    repo = InMemoryArtifactRepository()
    storage = FakeStorage()
    return ArtifactEngineService(repo, storage), repo, storage


def create_empty(service: ArtifactEngineService, org: UUID, project: UUID):
    return service.create_artifact(
        ArtifactCreateCommand(
            organization_id=org,
            project_id=project,
            artifact_type=ArtifactType.RASTER_IMAGE,
            name="poster",
            rights=rights(),
            created_by_type=CreatedByType.USER,
            created_by_id="user-1",
            created_at=NOW,
        )
    )


def create_version(service, storage, org, branch_id, head, key, *, lineage=()):
    file = artifact_file(org, key)
    storage.add(org, file.bucket, file.storage_key)
    return service.create_version(
        VersionCreateCommand(
            branch_id=branch_id,
            expected_head_version_id=head,
            content_hash=SHA,
            files=(file,),
            primary_file_id=file.id,
            provenance=provenance(),
            rights=rights(),
            created_by_type=CreatedByType.USER,
            created_by_id="user-1",
            created_at=NOW,
            constraint_snapshot_hash="2" * 64,
            lineage_sources=lineage,
        )
    )[0]


def test_create_artifact_main_and_optional_v1_are_atomic():
    service, repo, storage = service_pair()
    org, project = new_uuid7(), new_uuid7()
    file = artifact_file(org, "initial.png")
    storage.add(org, file.bucket, file.storage_key)
    artifact, branch = service.create_artifact(
        ArtifactCreateCommand(
            organization_id=org,
            project_id=project,
            artifact_type=ArtifactType.RASTER_IMAGE,
            name="poster",
            rights=rights(),
            created_by_type=CreatedByType.USER,
            created_by_id="u",
            created_at=NOW,
            initial_version=InitialVersionCreateCommand(
                content_hash=SHA,
                files=(file,),
                primary_file_id=file.id,
                provenance=provenance(),
                rights=rights(),
                created_by_type=CreatedByType.USER,
                created_by_id="u",
                constraint_snapshot_hash="2" * 64,
            ),
        )
    )
    assert branch.head_version_id is not None
    assert branch.base_version_id == branch.head_version_id
    assert repo.get_version(branch.head_version_id).artifact_id == artifact.id
    assert [event.event_type for event in repo.outbox] == [
        "artifact.created",
        "artifact.version.created",
    ]


def test_concurrent_branch_head_compare_and_swap_allows_one_winner():
    service, repo, storage = service_pair()
    org, project = new_uuid7(), new_uuid7()
    _, branch = create_empty(service, org, project)
    v1 = create_version(service, storage, org, branch.id, None, "v1.png")
    barrier = Barrier(2)
    results: list[str] = []

    def writer(index: int) -> None:
        file = artifact_file(org, f"v2-{index}.png")
        storage.add(org, file.bucket, file.storage_key)
        barrier.wait()
        try:
            service.create_version(
                VersionCreateCommand(
                    branch_id=branch.id,
                    expected_head_version_id=v1.id,
                    content_hash=str(index + 3) * 64,
                    files=(file,),
                    primary_file_id=file.id,
                    provenance=provenance(),
                    rights=rights(),
                    created_by_type=CreatedByType.USER,
                    created_by_id=f"u-{index}",
                    created_at=NOW,
                    constraint_snapshot_hash="2" * 64,
                )
            )
            results.append("ok")
        except ArtifactHeadConflict:
            results.append("conflict")

    threads = [Thread(target=writer, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["conflict", "ok"]
    assert len(repo.list_versions(v1.artifact_id)) == 2


def test_fork_restore_and_multi_parent_lineage():
    service, repo, storage = service_pair()
    org, project = new_uuid7(), new_uuid7()
    _, main = create_empty(service, org, project)
    v1 = create_version(service, storage, org, main.id, None, "v1.png")
    v2 = create_version(service, storage, org, main.id, v1.id, "v2.png")
    branch = service.fork_version(
        v1.id,
        name="alt",
        created_by_type=CreatedByType.USER,
        created_by_id="u",
        created_at=NOW,
    )
    assert branch.base_version_id == v1.id == branch.head_version_id
    restored, edges = service.restore_version(
        v1.id,
        target_branch_id=main.id,
        expected_head_version_id=v2.id,
        provenance=provenance(v1.id),
        created_by_type=CreatedByType.USER,
        created_by_id="u",
        created_at=NOW,
    )
    assert restored.id != v1.id
    assert restored.parent_version_id == v2.id
    assert {edge.type for edge in edges} == {
        LineageEdgeType.DERIVED_FROM,
        LineageEdgeType.EDITED_FROM,
    }
    assert restored.files[0].id != v1.files[0].id
    assert restored.files[0].storage_key == v1.files[0].storage_key


def test_approved_version_is_terminal():
    service, _, storage = service_pair()
    org, project = new_uuid7(), new_uuid7()
    _, branch = create_empty(service, org, project)
    version = create_version(service, storage, org, branch.id, None, "v1.png")
    ready = service.mark_ready(version.id, occurred_at=NOW)
    approved, _ = service.approve_version(
        ready.id,
        approved_by_id="reviewer",
        approved_at=NOW,
        validation_ref="validation://node39/pass",
    )
    assert approved.status.value == "APPROVED"
    with pytest.raises(ArtifactContractError):
        service.mark_ready(approved.id, occurred_at=NOW)


def test_missing_storage_is_rejected_before_version_append():
    service, repo, _ = service_pair()
    org, project = new_uuid7(), new_uuid7()
    _, branch = create_empty(service, org, project)
    file = artifact_file(org, "missing.png")
    with pytest.raises(ArtifactStorageViolation):
        service.create_version(
            VersionCreateCommand(
                branch_id=branch.id,
                expected_head_version_id=None,
                content_hash=SHA,
                files=(file,),
                primary_file_id=file.id,
                provenance=provenance(),
                rights=rights(),
                created_by_type=CreatedByType.USER,
                created_by_id="u",
                created_at=NOW,
                constraint_snapshot_hash="2" * 64,
            )
        )
    assert repo.list_versions(branch.artifact_id) == ()


def test_cross_tenant_equal_hash_does_not_share_authorization_scope():
    service, repo, storage = service_pair()
    org1, org2 = new_uuid7(), new_uuid7()
    _, b1 = create_empty(service, org1, new_uuid7())
    _, b2 = create_empty(service, org2, new_uuid7())
    v1 = create_version(service, storage, org1, b1.id, None, "same-hash.png")
    v2 = create_version(service, storage, org2, b2.id, None, "same-hash.png")
    assert v1.content_hash == v2.content_hash
    assert v1.organization_id != v2.organization_id
    assert v1.files[0].bucket != v2.files[0].bucket
    assert len(repo.list_versions(v1.artifact_id)) == 1
    assert len(repo.list_versions(v2.artifact_id)) == 1


def test_gc_marks_orphans_and_rechecks_live_references():
    service, _, storage = service_pair()
    org, project = new_uuid7(), new_uuid7()
    _, branch = create_empty(service, org, project)
    version = create_version(service, storage, org, branch.id, None, "live.png")
    orphan = StorageObjectMetadata(
        organization_id=org,
        bucket=f"org-{org}",
        storage_key="orphan.png",
        checksum_sha256="9" * 64,
        size_bytes=10,
        mime_type="image/png",
    )
    storage.objects[(org, orphan.bucket, orphan.storage_key)] = orphan
    marks = service.mark_gc_candidates(org, marked_at=NOW, delay=timedelta(hours=1))
    assert [mark.storage_key for mark in marks] == ["orphan.png"]
    audits = service.sweep_gc(org, checked_at=NOW + timedelta(hours=2))
    assert [audit.action for audit in audits] == ["DELETED"]
    assert storage.stat_object(org, version.files[0].bucket, version.files[0].storage_key)
