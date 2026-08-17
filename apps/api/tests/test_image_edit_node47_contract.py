from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from lumi_api.api.v1.image_edit_schemas import SubmitImageEditRequest
from lumi_api.image_edit.postgres_codec import decode_spec, encode_spec
from lumi_image_edit import EditIntent, ImageEditSpec, SourceImageRef

ORG = UUID("01910000-0000-7000-8000-000000004711")
PROJECT = UUID("01910000-0000-7000-8000-000000004712")
TASK = UUID("01910000-0000-7000-8000-000000004713")
OPERATION = UUID("01910000-0000-7000-8000-000000004714")
ARTIFACT = UUID("01910000-0000-7000-8000-000000004715")
VERSION = UUID("01910000-0000-7000-8000-000000004716")
ASSET = UUID("01910000-0000-7000-8000-000000004717")
SHA = "a" * 64
GIT = "b" * 40


def _payload() -> dict:
    return {
        "task_id": str(TASK),
        "operation_id": str(OPERATION),
        "source": {
            "artifact_id": str(ARTIFACT),
            "artifact_version_id": str(VERSION),
            "asset_id": str(ASSET),
            "asset_version": "7",
            "durable_ref": "bucket/source.png",
            "checksum_sha256": SHA,
            "width": 1000,
            "height": 1000,
            "mime_type": "image/png",
            "rights_assertion": "owned",
            "commercial_use_allowed": True,
        },
        "intent": {
            "action": "RELIGHT",
            "instruction": "Relight only the background",
        },
        "budget_limit_usd": "1.25",
        "agent_version": "agent-47.1",
        "recipe_version": "recipe-47.1",
        "skill_versions": {"local-edit": "1.0.0"},
    }


def test_api_never_accepts_client_lifecycle_approval_fields() -> None:
    payload = _payload()
    payload["intent"]["broad_change_confirmed"] = True
    with pytest.raises(ValidationError):
        SubmitImageEditRequest.model_validate(payload)

    payload = _payload()
    payload["mask"] = {
        "mask_id": "01910000-0000-7000-8000-000000004718",
        "version": "1",
        "source": "AGENT_PROPOSED",
        "source_asset_id": str(ASSET),
        "source_asset_version": "7",
        "source_checksum_sha256": SHA,
        "source_width": 1000,
        "source_height": 1000,
        "editable_rect": {"x": 0, "y": 0, "width": 400, "height": 1000},
        "checksum_sha256": "c" * 64,
        "durable_ref": "bucket/mask.png",
        "preview_required": True,
        "preview_approved_by": "spoofed-user",
    }
    with pytest.raises(ValidationError):
        SubmitImageEditRequest.model_validate(payload)


def test_schema_and_postgres_codec_preserve_provenance_inputs() -> None:
    body = SubmitImageEditRequest.model_validate(_payload())
    spec = body.to_domain(
        organization_id=ORG,
        project_id=PROJECT,
        code_git_sha=GIT,
    )
    restored = decode_spec(encode_spec(spec))
    assert restored == spec
    assert restored.agent_version == "agent-47.1"
    assert restored.recipe_version == "recipe-47.1"
    assert restored.skill_versions == {"local-edit": "1.0.0"}


def test_domain_codec_restores_decimal_and_tuple_semantics() -> None:
    source = SourceImageRef(
        str(ORG),
        str(PROJECT),
        str(ARTIFACT),
        str(VERSION),
        str(ASSET),
        "7",
        "bucket/source.png",
        SHA,
        1000,
        1000,
        "image/png",
        "owned",
        True,
    )
    spec = ImageEditSpec(
        str(ORG),
        str(PROJECT),
        str(TASK),
        str(OPERATION),
        source,
        EditIntent("RELIGHT", "relight"),
        (),
        (),
        None,
        None,
        (),
        Decimal("1.25"),
        GIT,
    )
    restored = decode_spec(encode_spec(spec))
    assert restored == spec
    assert isinstance(restored.identity_requirement_ids, tuple)
    assert isinstance(restored.budget_limit_usd, Decimal)
