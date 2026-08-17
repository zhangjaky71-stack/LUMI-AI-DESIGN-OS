from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from lumi_api.export_engine.snapshot_adapter import Node42ArtifactSnapshotAdapter


class EnumValue:
    def __init__(self, value: str) -> None:
        self.value = value


class Repository:
    def __init__(self, *, approved: bool = True) -> None:
        self.version_id = UUID("33333333-3333-4333-8333-333333333333")
        self.artifact_id = UUID("44444444-4444-4444-8444-444444444444")
        self.organization_id = UUID("11111111-1111-4111-8111-111111111111")
        self.project_id = UUID("22222222-2222-4222-8222-222222222222")
        self.calls = []
        self.version = SimpleNamespace(
            id=self.version_id,
            organization_id=self.organization_id,
            artifact_id=self.artifact_id,
            version_number=7,
            status=EnumValue("APPROVED" if approved else "READY"),
            content_hash="a" * 64,
            primary_file_id=UUID("55555555-5555-4555-8555-555555555555"),
            files=(
                SimpleNamespace(
                    id=UUID("55555555-5555-4555-8555-555555555555"),
                    role=EnumValue("ORIGINAL"),
                    bucket="artifact-bucket",
                    storage_key="objects/hero.png",
                    mime_type="image/png",
                    size_bytes=100,
                    checksum_sha256="b" * 64,
                ),
            ),
            rights=SimpleNamespace(review_status=EnumValue("UNREVIEWED")),
        )
        self.artifact = SimpleNamespace(
            id=self.artifact_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            type=EnumValue("IMAGE"),
        )

    def get_version(self, version_id):
        self.calls.append(("get_version", version_id))
        return self.version

    def get_artifact(self, artifact_id):
        self.calls.append(("get_artifact", artifact_id))
        return self.artifact


def test_snapshot_adapter_reads_only_exact_version_and_never_head():
    repository = Repository()
    adapter = Node42ArtifactSnapshotAdapter(repository)  # type: ignore[arg-type]
    snapshot = adapter.snapshot_exact(
        organization_id=str(repository.organization_id),
        project_id=str(repository.project_id),
        artifact_version_id=str(repository.version_id),
    )
    assert snapshot.artifact_version_id == str(repository.version_id)
    assert repository.calls == [
        ("get_version", repository.version_id),
        ("get_artifact", repository.artifact_id),
    ]


def test_snapshot_adapter_rejects_nonapproved_version():
    repository = Repository(approved=False)
    adapter = Node42ArtifactSnapshotAdapter(repository)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="NOT_APPROVED"):
        adapter.snapshot_exact(
            organization_id=str(repository.organization_id),
            project_id=str(repository.project_id),
            artifact_version_id=str(repository.version_id),
        )
