from __future__ import annotations

from decimal import Decimal

import pytest

from lumi_video_generation.model import (
    AudioTrackSpec,
    ContinuityRef,
    IdentityRequirement,
    ShotSpec,
    SourceImageRef,
    VideoTaskSpec,
)
from lumi_video_generation.spec_codec import VIDEO_SPEC_SCHEMA_VERSION, decode_spec, encode_spec


def _source() -> SourceImageRef:
    return SourceImageRef(
        asset_id="asset-1",
        asset_version="v3",
        durable_ref="asset:asset-1@v3",
        checksum_sha256="a" * 64,
        commercial_use_allowed=True,
        artifact_version_id="artifact-version-1",
    )


def _spec() -> VideoTaskSpec:
    source = _source()
    return VideoTaskSpec(
        organization_id="00000000-0000-0000-0000-000000000001",
        project_id="00000000-0000-0000-0000-000000000002",
        task_id="00000000-0000-0000-0000-000000000003",
        operation_id="00000000-0000-0000-0000-000000000004",
        mode="STORYBOARD_MULTI_SHOT",
        prompt="Cinematic launch",
        duration_seconds=Decimal("4.500"),
        aspect_ratio="16:9",
        width=1600,
        height=900,
        fps=24,
        budget_limit_usd=Decimal("2.75000000"),
        code_git_sha="b" * 40,
        source_images=(source,),
        shots=(
            ShotSpec(
                shot_id="hero",
                duration_seconds=Decimal("2.250"),
                prompt="Hero reveal",
                source_ref=source,
                continuity_refs=(ContinuityRef(kind="FIRST_FRAME", durable_ref="asset:first-frame"),),
                transition_to_next="CUT",
            ),
            ShotSpec(
                shot_id="detail",
                duration_seconds=Decimal("2.250"),
                prompt="Detail motion",
                continuity_refs=(ContinuityRef(kind="PREVIOUS_TAIL", source_shot_id="hero"),),
                optional=True,
            ),
        ),
        audio_tracks=(
            AudioTrackSpec(
                durable_ref="asset:audio-bed",
                offset_seconds=Decimal("0.250"),
                gain_db=Decimal("-3.5"),
            ),
        ),
        brand_rule_set_version="brand-v7",
        identity_requirements=(
            IdentityRequirement(
                identity_id="product-identity",
                reference_set_version="identity-v2",
                severity="HARD",
            ),
        ),
        agent_run_id="00000000-0000-0000-0000-000000000005",
        recipe_version="video-recipe-v4",
        allow_optional_shot_drop=True,
        quality_retry_limit=2,
        negative_prompt="No text overlays",
        seed=42,
        metadata={"campaign": "launch", "flags": ["rc", 7, True]},
    )


def test_video_spec_round_trip_preserves_semantic_hash_and_decimals() -> None:
    spec = _spec()
    encoded = encode_spec(spec)
    decoded = decode_spec(encoded)

    assert encoded["schema_version"] == VIDEO_SPEC_SCHEMA_VERSION
    assert encoded["duration_seconds"] == "4.500"
    assert encoded["budget_limit_usd"] == "2.75000000"
    assert decoded == spec
    assert decoded.semantic_hash == spec.semantic_hash


def test_video_spec_rejects_unknown_fields() -> None:
    payload = encode_spec(_spec())
    payload["provider_api_key"] = "forbidden"
    with pytest.raises(ValueError, match="VIDEO_SPEC_FIELDS_UNKNOWN"):
        decode_spec(payload)


def test_video_spec_rejects_numeric_decimal_transport() -> None:
    payload = encode_spec(_spec())
    payload["budget_limit_usd"] = 2.75
    with pytest.raises(ValueError, match="VIDEO_SPEC_BUDGET_INVALID"):
        decode_spec(payload)


def test_video_spec_rejects_schema_drift() -> None:
    payload = encode_spec(_spec())
    payload["schema_version"] = 2
    with pytest.raises(ValueError, match="VIDEO_SPEC_SCHEMA_UNSUPPORTED"):
        decode_spec(payload)


def test_video_spec_rejects_unknown_transition() -> None:
    payload = encode_spec(_spec())
    shots = payload["shots"]
    assert isinstance(shots, list)
    assert isinstance(shots[0], dict)
    shots[0]["transition_to_next"] = "MORPH"
    with pytest.raises(ValueError, match="VIDEO_SHOT_TRANSITION_INVALID"):
        decode_spec(payload)
