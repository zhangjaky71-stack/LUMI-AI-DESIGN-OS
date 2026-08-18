from __future__ import annotations

import inspect
from datetime import datetime, timezone

from lumi_api.api.v1.artifact_engine_schemas import (
    SafeVersionProvenanceResponse,
    UserForkVersionRequest,
    UserRestoreVersionRequest,
)
from lumi_api.api.v1.version_history_routes import _history_item, restore_artifact_version_for_user
from lumi_api.artifacts.models import (
    ArtifactFile,
    ArtifactVersion,
    ArtifactVersionStatus,
    CreatedByType,
    FileRole,
    ProvenanceRecord,
    RightsPolicy,
)
from lumi_api.domain.ids import new_uuid7

SHA = "1" * 64
GIT = "a" * 40
NOW = datetime(2026, 8, 18, 4, 30, tzinfo=timezone.utc)


def _rights() -> RightsPolicy:
    return RightsPolicy(
        source_type="user-upload",
        owner_assertion="owned by tenant",
        license_type="owned",
        commercial_use=True,
    )


def _version() -> ArtifactVersion:
    file = ArtifactFile(
        id=new_uuid7(),
        role=FileRole.ORIGINAL,
        bucket="private-bucket",
        storage_key="tenant/secret/object.png",
        mime_type="image/png",
        size_bytes=99,
        checksum_sha256=SHA,
        width=1200,
        height=800,
    )
    return ArtifactVersion(
        id=new_uuid7(),
        organization_id=new_uuid7(),
        artifact_id=new_uuid7(),
        branch_id=new_uuid7(),
        version_number=3,
        status=ArtifactVersionStatus.APPROVED,
        content_hash=SHA,
        primary_file_id=file.id,
        quality_score=0.91,
        created_by_type=CreatedByType.AGENT,
        created_by_id="agent-design-v4",
        created_at=NOW,
        files=(file,),
        provenance=ProvenanceRecord(
            provider="provider-x",
            model="model-y",
            prompt_hash="2" * 64,
            prompt_ref="internal://prompt/private",
            provider_request_id="provider-secret-request-ref",
            code_git_sha=GIT,
        ),
        rights=_rights(),
    )


def test_version_history_projection_does_not_leak_storage_or_provenance() -> None:
    projected = _history_item(_version()).model_dump(mode="json")
    serialized = repr(projected)
    assert "storage_key" not in serialized
    assert "private-bucket" not in serialized
    assert "prompt_ref" not in serialized
    assert "provider_request_id" not in serialized
    assert projected["preview"] == {
        "mime_type": "image/png",
        "width": 1200,
        "height": 800,
        "duration_ms": None,
    }


def test_safe_provenance_schema_is_allowlisted() -> None:
    fields = set(SafeVersionProvenanceResponse.model_fields)
    assert "prompt_hash" in fields
    assert "provider" in fields
    assert "model" in fields
    assert "input_artifact_version_ids" in fields
    assert "prompt_ref" not in fields
    assert "provider_request_id" not in fields
    assert "messages" not in fields
    assert "reasoning" not in fields


def test_user_mutation_requests_cannot_supply_creator_or_provenance() -> None:
    assert set(UserForkVersionRequest.model_fields) == {"name"}
    assert set(UserRestoreVersionRequest.model_fields) == {
        "target_branch_id",
        "expected_head_version_id",
    }


def test_user_restore_route_is_head_fenced_and_server_provenanced() -> None:
    source = inspect.getsource(restore_artifact_version_for_user)
    assert "expected_head_version_id=body.expected_head_version_id" in source
    assert "input_artifact_version_ids=(source.id,)" in source
    assert "created_by_type=CreatedByType.USER" in source
    assert "created_by_id=_actor_id(request)" in source
    assert "return _history_item" in source
    assert "body.provenance" not in source
    assert "body.created_by" not in source
