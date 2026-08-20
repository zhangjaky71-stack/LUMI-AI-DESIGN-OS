from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

from .model import (
    AudioTrackSpec,
    ContinuityRef,
    IdentityRequirement,
    ShotSpec,
    SourceImageRef,
    VideoMode,
    VideoTaskSpec,
)

VIDEO_SPEC_SCHEMA_VERSION = 1


def encode_spec(spec: VideoTaskSpec) -> dict[str, Any]:
    return {
        "schema_version": VIDEO_SPEC_SCHEMA_VERSION,
        "organization_id": spec.organization_id,
        "project_id": spec.project_id,
        "task_id": spec.task_id,
        "operation_id": spec.operation_id,
        "mode": spec.mode,
        "prompt": spec.prompt,
        "duration_seconds": format(spec.duration_seconds, "f"),
        "aspect_ratio": spec.aspect_ratio,
        "width": spec.width,
        "height": spec.height,
        "fps": spec.fps,
        "budget_limit_usd": format(spec.budget_limit_usd, "f"),
        "code_git_sha": spec.code_git_sha,
        "source_images": [_encode_source(value) for value in spec.source_images],
        "shots": [_encode_shot(value) for value in spec.shots],
        "audio_tracks": [_encode_audio(value) for value in spec.audio_tracks],
        "brand_rule_set_version": spec.brand_rule_set_version,
        "identity_requirements": [_encode_identity(value) for value in spec.identity_requirements],
        "agent_run_id": spec.agent_run_id,
        "recipe_version": spec.recipe_version,
        "allow_optional_shot_drop": spec.allow_optional_shot_drop,
        "quality_retry_limit": spec.quality_retry_limit,
        "negative_prompt": spec.negative_prompt,
        "seed": spec.seed,
        "metadata": _json_object(dict(spec.metadata), label="VIDEO_SPEC_METADATA"),
    }


def decode_spec(value: object) -> VideoTaskSpec:
    payload = _object(value, "VIDEO_SPEC_OBJECT_REQUIRED")
    expected = {
        "schema_version",
        "organization_id",
        "project_id",
        "task_id",
        "operation_id",
        "mode",
        "prompt",
        "duration_seconds",
        "aspect_ratio",
        "width",
        "height",
        "fps",
        "budget_limit_usd",
        "code_git_sha",
        "source_images",
        "shots",
        "audio_tracks",
        "brand_rule_set_version",
        "identity_requirements",
        "agent_run_id",
        "recipe_version",
        "allow_optional_shot_drop",
        "quality_retry_limit",
        "negative_prompt",
        "seed",
        "metadata",
    }
    _exact_fields(payload, expected, "VIDEO_SPEC_FIELDS")
    if payload["schema_version"] != VIDEO_SPEC_SCHEMA_VERSION:
        raise ValueError("VIDEO_SPEC_SCHEMA_UNSUPPORTED")
    mode = _string(payload["mode"], "VIDEO_SPEC_MODE_REQUIRED")
    if mode not in {"TEXT_TO_VIDEO", "IMAGE_TO_VIDEO", "STORYBOARD_MULTI_SHOT"}:
        raise ValueError("VIDEO_SPEC_MODE_INVALID")
    return VideoTaskSpec(
        organization_id=_string(payload["organization_id"], "VIDEO_SPEC_ORGANIZATION_REQUIRED"),
        project_id=_string(payload["project_id"], "VIDEO_SPEC_PROJECT_REQUIRED"),
        task_id=_string(payload["task_id"], "VIDEO_SPEC_TASK_REQUIRED"),
        operation_id=_string(payload["operation_id"], "VIDEO_SPEC_OPERATION_REQUIRED"),
        mode=cast(VideoMode, mode),
        prompt=_string(payload["prompt"], "VIDEO_SPEC_PROMPT_REQUIRED"),
        duration_seconds=_decimal(payload["duration_seconds"], "VIDEO_SPEC_DURATION_INVALID"),
        aspect_ratio=_string(payload["aspect_ratio"], "VIDEO_SPEC_ASPECT_RATIO_REQUIRED"),
        width=_integer(payload["width"], "VIDEO_SPEC_WIDTH_INVALID"),
        height=_integer(payload["height"], "VIDEO_SPEC_HEIGHT_INVALID"),
        fps=_integer(payload["fps"], "VIDEO_SPEC_FPS_INVALID"),
        budget_limit_usd=_decimal(payload["budget_limit_usd"], "VIDEO_SPEC_BUDGET_INVALID"),
        code_git_sha=_string(payload["code_git_sha"], "VIDEO_SPEC_CODE_SHA_REQUIRED"),
        source_images=tuple(_decode_source(item) for item in _list(payload["source_images"], "VIDEO_SPEC_SOURCES_INVALID")),
        shots=tuple(_decode_shot(item) for item in _list(payload["shots"], "VIDEO_SPEC_SHOTS_INVALID")),
        audio_tracks=tuple(_decode_audio(item) for item in _list(payload["audio_tracks"], "VIDEO_SPEC_AUDIO_INVALID")),
        brand_rule_set_version=_optional_string(payload["brand_rule_set_version"], "VIDEO_SPEC_BRAND_INVALID"),
        identity_requirements=tuple(
            _decode_identity(item)
            for item in _list(payload["identity_requirements"], "VIDEO_SPEC_IDENTITIES_INVALID")
        ),
        agent_run_id=_optional_string(payload["agent_run_id"], "VIDEO_SPEC_AGENT_RUN_INVALID"),
        recipe_version=_optional_string(payload["recipe_version"], "VIDEO_SPEC_RECIPE_INVALID"),
        allow_optional_shot_drop=_boolean(payload["allow_optional_shot_drop"], "VIDEO_SPEC_OPTIONAL_DROP_INVALID"),
        quality_retry_limit=_integer(payload["quality_retry_limit"], "VIDEO_SPEC_RETRY_LIMIT_INVALID"),
        negative_prompt=_optional_string(payload["negative_prompt"], "VIDEO_SPEC_NEGATIVE_PROMPT_INVALID"),
        seed=_optional_integer(payload["seed"], "VIDEO_SPEC_SEED_INVALID"),
        metadata=MappingProxyType(_json_object(payload["metadata"], label="VIDEO_SPEC_METADATA")),
    )


def _encode_source(value: SourceImageRef) -> dict[str, Any]:
    return {
        "asset_id": value.asset_id,
        "asset_version": value.asset_version,
        "durable_ref": value.durable_ref,
        "checksum_sha256": value.checksum_sha256,
        "commercial_use_allowed": value.commercial_use_allowed,
        "artifact_version_id": value.artifact_version_id,
    }


def _decode_source(value: object) -> SourceImageRef:
    payload = _object(value, "VIDEO_SOURCE_OBJECT_REQUIRED")
    _exact_fields(
        payload,
        {"asset_id", "asset_version", "durable_ref", "checksum_sha256", "commercial_use_allowed", "artifact_version_id"},
        "VIDEO_SOURCE_FIELDS",
    )
    return SourceImageRef(
        asset_id=_string(payload["asset_id"], "VIDEO_SOURCE_ASSET_ID_REQUIRED"),
        asset_version=_string(payload["asset_version"], "VIDEO_SOURCE_ASSET_VERSION_REQUIRED"),
        durable_ref=_string(payload["durable_ref"], "VIDEO_SOURCE_DURABLE_REF_REQUIRED"),
        checksum_sha256=_string(payload["checksum_sha256"], "VIDEO_SOURCE_CHECKSUM_REQUIRED"),
        commercial_use_allowed=_boolean(payload["commercial_use_allowed"], "VIDEO_SOURCE_COMMERCIAL_INVALID"),
        artifact_version_id=_optional_string(payload["artifact_version_id"], "VIDEO_SOURCE_ARTIFACT_VERSION_INVALID"),
    )


def _encode_identity(value: IdentityRequirement) -> dict[str, Any]:
    return {
        "identity_id": value.identity_id,
        "reference_set_version": value.reference_set_version,
        "severity": value.severity,
    }


def _decode_identity(value: object) -> IdentityRequirement:
    payload = _object(value, "VIDEO_IDENTITY_OBJECT_REQUIRED")
    _exact_fields(payload, {"identity_id", "reference_set_version", "severity"}, "VIDEO_IDENTITY_FIELDS")
    severity = _string(payload["severity"], "VIDEO_IDENTITY_SEVERITY_REQUIRED")
    if severity not in {"HARD", "SOFT", "ADVISORY"}:
        raise ValueError("VIDEO_IDENTITY_SEVERITY_INVALID")
    return IdentityRequirement(
        identity_id=_string(payload["identity_id"], "VIDEO_IDENTITY_ID_REQUIRED"),
        reference_set_version=_string(payload["reference_set_version"], "VIDEO_IDENTITY_VERSION_REQUIRED"),
        severity=cast(Any, severity),
    )


def _encode_continuity(value: ContinuityRef) -> dict[str, Any]:
    return {
        "kind": value.kind,
        "durable_ref": value.durable_ref,
        "source_shot_id": value.source_shot_id,
    }


def _decode_continuity(value: object) -> ContinuityRef:
    payload = _object(value, "VIDEO_CONTINUITY_OBJECT_REQUIRED")
    _exact_fields(payload, {"kind", "durable_ref", "source_shot_id"}, "VIDEO_CONTINUITY_FIELDS")
    kind = _string(payload["kind"], "VIDEO_CONTINUITY_KIND_REQUIRED")
    if kind not in {"FIRST_FRAME", "PREVIOUS_TAIL", "EXPLICIT_REFERENCE"}:
        raise ValueError("VIDEO_CONTINUITY_KIND_INVALID")
    return ContinuityRef(
        kind=cast(Any, kind),
        durable_ref=_optional_string(payload["durable_ref"], "VIDEO_CONTINUITY_REF_INVALID"),
        source_shot_id=_optional_string(payload["source_shot_id"], "VIDEO_CONTINUITY_SHOT_INVALID"),
    )


def _encode_shot(value: ShotSpec) -> dict[str, Any]:
    return {
        "shot_id": value.shot_id,
        "duration_seconds": format(value.duration_seconds, "f"),
        "prompt": value.prompt,
        "camera_motion": value.camera_motion,
        "subject_action": value.subject_action,
        "source_ref": _encode_source(value.source_ref) if value.source_ref is not None else None,
        "continuity_refs": [_encode_continuity(item) for item in value.continuity_refs],
        "transition_to_next": value.transition_to_next,
        "optional": value.optional,
    }


def _decode_shot(value: object) -> ShotSpec:
    payload = _object(value, "VIDEO_SHOT_OBJECT_REQUIRED")
    _exact_fields(
        payload,
        {"shot_id", "duration_seconds", "prompt", "camera_motion", "subject_action", "source_ref", "continuity_refs", "transition_to_next", "optional"},
        "VIDEO_SHOT_FIELDS",
    )
    transition = _string(payload["transition_to_next"], "VIDEO_SHOT_TRANSITION_REQUIRED")
    if transition not in {"CUT", "CROSSFADE"}:
        raise ValueError("VIDEO_SHOT_TRANSITION_INVALID")
    source = payload["source_ref"]
    return ShotSpec(
        shot_id=_string(payload["shot_id"], "VIDEO_SHOT_ID_REQUIRED"),
        duration_seconds=_decimal(payload["duration_seconds"], "VIDEO_SHOT_DURATION_INVALID"),
        prompt=_string(payload["prompt"], "VIDEO_SHOT_PROMPT_REQUIRED"),
        camera_motion=_optional_string(payload["camera_motion"], "VIDEO_SHOT_CAMERA_INVALID"),
        subject_action=_optional_string(payload["subject_action"], "VIDEO_SHOT_ACTION_INVALID"),
        source_ref=_decode_source(source) if source is not None else None,
        continuity_refs=tuple(
            _decode_continuity(item)
            for item in _list(payload["continuity_refs"], "VIDEO_SHOT_CONTINUITY_INVALID")
        ),
        transition_to_next=cast(Any, transition),
        optional=_boolean(payload["optional"], "VIDEO_SHOT_OPTIONAL_INVALID"),
    )


def _encode_audio(value: AudioTrackSpec) -> dict[str, Any]:
    return {
        "durable_ref": value.durable_ref,
        "offset_seconds": format(value.offset_seconds, "f"),
        "gain_db": format(value.gain_db, "f"),
    }


def _decode_audio(value: object) -> AudioTrackSpec:
    payload = _object(value, "VIDEO_AUDIO_OBJECT_REQUIRED")
    _exact_fields(payload, {"durable_ref", "offset_seconds", "gain_db"}, "VIDEO_AUDIO_FIELDS")
    return AudioTrackSpec(
        durable_ref=_string(payload["durable_ref"], "VIDEO_AUDIO_REF_REQUIRED"),
        offset_seconds=_decimal(payload["offset_seconds"], "VIDEO_AUDIO_OFFSET_INVALID"),
        gain_db=_decimal(payload["gain_db"], "VIDEO_AUDIO_GAIN_INVALID"),
    )


def _object(value: object, error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(error)
    return value


def _exact_fields(payload: dict[str, Any], expected: set[str], label: str) -> None:
    unknown = set(payload) - expected
    missing = expected - set(payload)
    if unknown:
        raise ValueError(f"{label}_UNKNOWN:{','.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{label}_MISSING:{','.join(sorted(missing))}")


def _string(value: object, error: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(error)
    return value


def _optional_string(value: object, error: str) -> str | None:
    if value is None:
        return None
    return _string(value, error)


def _integer(value: object, error: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error)
    return value


def _optional_integer(value: object, error: str) -> int | None:
    if value is None:
        return None
    return _integer(value, error)


def _boolean(value: object, error: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(error)
    return value


def _decimal(value: object, error: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(error)
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError(error) from exc
    if not result.is_finite():
        raise ValueError(error)
    return result


def _list(value: object, error: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(error)
    return value


def _json_object(value: object, *, label: str, depth: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label}_OBJECT_REQUIRED")
    if depth > 12:
        raise ValueError(f"{label}_TOO_DEEP")
    return {key: _json_value(item, label=label, depth=depth + 1) for key, item in value.items()}


def _json_value(value: object, *, label: str, depth: int) -> Any:
    if depth > 12:
        raise ValueError(f"{label}_TOO_DEEP")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"{label}_NON_FINITE")
        return value
    if isinstance(value, list):
        return [_json_value(item, label=label, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item, label=label, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        return _json_object(value, label=label, depth=depth + 1)
    raise ValueError(f"{label}_VALUE_INVALID:{type(value).__name__}")
