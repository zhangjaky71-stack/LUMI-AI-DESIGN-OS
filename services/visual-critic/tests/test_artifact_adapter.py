from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from lumi_api.visual_critic.artifact_adapter import Node42QualityArtifactAdapter


class EnumValue:
    def __init__(self, value: str) -> None:
        self.value = value


class Repository:
    def __init__(self) -> None:
        self.version_id = UUID("33333333-3333-4333-8333-333333333333")
        self.artifact_id = UUID("44444444-4444-4444-8444-444444444444")
        self.organization_id = UUID("11111111-1111-4111-8111-111111111111")
        self.project_id = UUID("22222222-2222-4222-8222-222222222222")
        self.calls = []
        file_id = UUID("55555555-5555-4555-8555-555555555555")
        self.version = SimpleNamespace(
            id=self.version_id,
            organization_id=self.organization_id,
            artifact_id=self.artifact_id,
            content_hash="a" * 64,
            primary_file_id=file_id,
            design_document_version_id=UUID("66666666-6666-4666-8666-666666666666"),
            status=EnumValue("READY"),
            constraint_snapshot_hash="b" * 64,
            files=(
                SimpleNamespace(
                    id=file_id,
                    bucket="artifact-bucket",
                    storage_key="objects/design.png",
                    mime_type="image/png",
                    size_bytes=4096,
                    width=1200,
                    height=1600,
                    duration_ms=None,
                    metadata=(
                        ("brand_rule_snapshot_id", "brand-v3"),
                        ("identity_refs", "product-v2,logo-v1"),
                        ("model_revision_id", "image-rev-8"),
                    ),
                ),
            ),
            provenance=SimpleNamespace(
                provider="generator-provider",
                model="image-model-v4",
            ),
        )
        self.artifact = SimpleNamespace(
            id=self.artifact_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            type=EnumValue("IMAGE"),
        )

    def get_version(self, value):
        self.calls.append(("get_version", value))
        return self.version

    def get_artifact(self, value):
        self.calls.append(("get_artifact", value))
        return self.artifact


def test_quality_artifact_adapter_uses_exact_version_without_head_lookup():
    repository = Repository()
    adapter = Node42QualityArtifactAdapter(repository)  # type: ignore[arg-type]
    result = adapter.load_exact(
        organization_id=str(repository.organization_id),
        project_id=str(repository.project_id),
        artifact_version_id=str(repository.version_id),
    )
    assert result.artifact_version_id == str(repository.version_id)
    assert result.design_ir_ref == "66666666-6666-4666-8666-666666666666"
    assert result.brand_rule_snapshot_id == "brand-v3"
    assert result.identity_refs == ("logo-v1", "product-v2")
    assert result.generation_model == "image-model-v4"
    assert repository.calls == [
        ("get_version", repository.version_id),
        ("get_artifact", repository.artifact_id),
    ]


def test_cross_project_artifact_is_rejected():
    repository = Repository()
    adapter = Node42QualityArtifactAdapter(repository)  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="PROJECT_MISMATCH"):
        adapter.load_exact(
            organization_id=str(repository.organization_id),
            project_id="77777777-7777-4777-8777-777777777777",
            artifact_version_id=str(repository.version_id),
        )
