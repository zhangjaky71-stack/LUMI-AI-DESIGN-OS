from datetime import UTC, datetime

import pytest

from lumi_artifacts import (
    Artifact,
    ArtifactBranch,
    ArtifactFile,
    ArtifactHistory,
    ArtifactVersion,
    BranchHeadConflict,
    CompilerProvenance,
    StoredObjectStat,
    advance_branch_head_cas,
    attach_verified_file,
    compiler_provenance_payload,
    next_version_number,
)

H = "a" * 64
C = "b" * 64


def seeded() -> ArtifactHistory:
    history = ArtifactHistory()
    history.add_artifact(Artifact("a1", "o1", "p1", "DESIGN_DOCUMENT", "LUMI"))
    history.add_branch(ArtifactBranch("b1", "o1", "a1", "main", None, None, "u1"))
    return history


def version(version_id: str, number: int, parent: str | None = None) -> ArtifactVersion:
    return ArtifactVersion(
        id=version_id,
        organization_id="o1",
        artifact_id="a1",
        branch_id="b1",
        parent_version_id=parent,
        schema_version="1.0",
        version_number=number,
        status="DRAFT",
        content_hash=H,
        constraint_snapshot_hash=C,
        created_by_type="USER",
        created_by_id="u1",
        created_at=datetime(2026, 8, 14, 0, 0, number, tzinfo=UTC),
    )


def test_branch_cas_and_monotonic_number() -> None:
    history = seeded()
    history.add_version(version("v1", 1))
    history.add_version(version("v2", 2, "v1"), advance_branch_head=False)
    with pytest.raises(BranchHeadConflict):
        advance_branch_head_cas(
            history,
            branch_id="b1",
            expected_head_version_id=None,
            next_head_version_id="v2",
        )
    advance_branch_head_cas(
        history,
        branch_id="b1",
        expected_head_version_id="v1",
        next_head_version_id="v2",
    )
    assert history.branches["b1"].head_version_id == "v2"
    assert next_version_number(history, "a1") == 3


def test_verified_storage_attach_is_fail_closed() -> None:
    history = seeded()
    history.add_version(version("v1", 1))
    file = ArtifactFile(
        id="f1",
        organization_id="o1",
        artifact_version_id="v1",
        role="PREVIEW",
        storage_key="org/o1/blob.png",
        mime_type="image/png",
        size_bytes=10,
        checksum_sha256=H,
    )

    class Missing:
        def stat(self, storage_key: str) -> None:
            return None

    class Valid:
        def stat(self, storage_key: str) -> StoredObjectStat:
            return StoredObjectStat(storage_key, 10, H, "image/png")

    with pytest.raises(ValueError, match="missing"):
        attach_verified_file(history, file, Missing())
    attach_verified_file(history, file, Valid())
    assert history.files["f1"] == file


def test_compiler_provenance_payload_is_deterministic() -> None:
    value = CompilerProvenance(
        compiler_version="1.0.0",
        document_id="doc",
        schema_version="1.0",
        document_version=4,
        resource_versions={"z": "2", "a": "1"},
        font_versions={"Inter": "4"},
        compile_hash=H,
    )
    payload = compiler_provenance_payload(value)
    assert list(payload["resource_versions"]) == ["a", "z"]
    assert payload["compile_hash"] == H
