from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from .model import (
    ConstraintSeverity,
    GenerationConstraint,
    GenerationMode,
    IdentityRequirement,
    ImageGenerationSpec,
    ImageReference,
    OutputFormat,
    OutputRequirements,
    QualityProfile,
    ReferenceRole,
    ReferenceSource,
)

SPEC_SCHEMA_VERSION = 1


def encode_spec(spec: ImageGenerationSpec) -> dict[str, Any]:
    """Encode the canonical NODE-46 image-generation spec snapshot.

    This wire shape is intentionally owned by the image-generation domain package so
    control-plane producers and worker consumers cannot evolve independent schemas.
    """

    return {
        "schema_version": SPEC_SCHEMA_VERSION,
        "spec": {
            "organization_id": spec.organization_id,
            "project_id": spec.project_id,
            "task_id": spec.task_id,
            "operation_id": spec.operation_id,
            "purpose": spec.purpose,
            "mode": spec.mode,
            "prompt_compilation_ref": spec.prompt_compilation_ref,
            "objective": spec.objective,
            "content": spec.content,
            "visual_direction": spec.visual_direction,
            "aspect_ratio": spec.aspect_ratio,
            "target_width": spec.target_width,
            "target_height": spec.target_height,
            "variant_count": spec.variant_count,
            "references": [_encode_reference(item) for item in spec.references],
            "identity_requirements": [
                _encode_identity_requirement(item) for item in spec.identity_requirements
            ],
            "brand_rule_set_version": spec.brand_rule_set_version,
            "constraints": [_encode_constraint(item) for item in spec.constraints],
            "quality_profile": spec.quality_profile,
            "budget_limit_usd": format(spec.budget_limit_usd, "f"),
            "output_requirements": _encode_output_requirements(spec.output_requirements),
            "code_git_sha": spec.code_git_sha,
            "agent_run_id": spec.agent_run_id,
            "recipe_version": spec.recipe_version,
            "skill_versions": dict(spec.skill_versions),
            "seed": spec.seed,
            "user_intent_ref": spec.user_intent_ref,
            "semantic_hash": spec.semantic_hash,
        },
    }


def decode_spec(payload: dict[str, Any]) -> ImageGenerationSpec:
    if payload.get("schema_version") != SPEC_SCHEMA_VERSION:
        raise ValueError("GENERATION_SPEC_SCHEMA_UNSUPPORTED")
    root = _dict(payload, "spec")
    raw_references = _list(root, "references")
    raw_identity = _list(root, "identity_requirements")
    raw_constraints = _list(root, "constraints")
    raw_skills = _dict(root, "skill_versions")

    spec = ImageGenerationSpec(
        organization_id=_str(root, "organization_id"),
        project_id=_str(root, "project_id"),
        task_id=_str(root, "task_id"),
        operation_id=_str(root, "operation_id"),
        purpose=_str(root, "purpose"),
        mode=cast(GenerationMode, _str(root, "mode")),
        prompt_compilation_ref=_str(root, "prompt_compilation_ref"),
        objective=_str(root, "objective"),
        content=_str(root, "content"),
        visual_direction=_str(root, "visual_direction", allow_empty=True),
        aspect_ratio=_str(root, "aspect_ratio"),
        target_width=_int(root, "target_width"),
        target_height=_int(root, "target_height"),
        variant_count=_int(root, "variant_count"),
        references=tuple(_decode_reference(_object(item)) for item in raw_references),
        identity_requirements=tuple(
            _decode_identity_requirement(_object(item)) for item in raw_identity
        ),
        brand_rule_set_version=_optional_str(root.get("brand_rule_set_version")),
        constraints=tuple(_decode_constraint(_object(item)) for item in raw_constraints),
        quality_profile=cast(QualityProfile, _str(root, "quality_profile")),
        budget_limit_usd=_decimal(root.get("budget_limit_usd"), "budget_limit_usd"),
        output_requirements=_decode_output_requirements(_dict(root, "output_requirements")),
        code_git_sha=_str(root, "code_git_sha"),
        agent_run_id=_optional_str(root.get("agent_run_id")),
        recipe_version=_optional_str(root.get("recipe_version")),
        skill_versions={
            _plain_key(key): _string_value(value, f"skill_versions.{key}")
            for key, value in raw_skills.items()
        },
        seed=_optional_int(root.get("seed"), "seed"),
        user_intent_ref=_optional_str(root.get("user_intent_ref")),
    )
    stored_hash = _str(root, "semantic_hash")
    if spec.semantic_hash != stored_hash:
        raise ValueError("GENERATION_SPEC_SEMANTIC_HASH_MISMATCH")
    return spec


def _encode_reference(value: ImageReference) -> dict[str, Any]:
    return {
        "asset_id": value.asset_id,
        "asset_version": value.asset_version,
        "role": value.role,
        "source": value.source,
        "note": value.note,
    }


def _decode_reference(payload: dict[str, Any]) -> ImageReference:
    return ImageReference(
        asset_id=_str(payload, "asset_id"),
        asset_version=_str(payload, "asset_version"),
        role=cast(ReferenceRole, _str(payload, "role")),
        source=cast(ReferenceSource, _str(payload, "source")),
        note=_optional_str(payload.get("note")),
    )


def _encode_identity_requirement(value: IdentityRequirement) -> dict[str, Any]:
    return {
        "identity_id": value.identity_id,
        "reference_set_version": value.reference_set_version,
        "severity": value.severity,
        "scenario": value.scenario,
    }


def _decode_identity_requirement(payload: dict[str, Any]) -> IdentityRequirement:
    return IdentityRequirement(
        identity_id=_str(payload, "identity_id"),
        reference_set_version=_str(payload, "reference_set_version"),
        severity=cast(ConstraintSeverity, _str(payload, "severity")),
        scenario=_str(payload, "scenario"),
    )


def _encode_constraint(value: GenerationConstraint) -> dict[str, Any]:
    return {
        "constraint_id": value.constraint_id,
        "constraint_type": value.constraint_type,
        "severity": value.severity,
        "snapshot_hash": value.snapshot_hash,
        "parameters": _json_value(dict(value.parameters)),
    }


def _decode_constraint(payload: dict[str, Any]) -> GenerationConstraint:
    return GenerationConstraint(
        constraint_id=_str(payload, "constraint_id"),
        constraint_type=_str(payload, "constraint_type"),
        severity=cast(ConstraintSeverity, _str(payload, "severity")),
        snapshot_hash=_str(payload, "snapshot_hash"),
        parameters=_dict(payload, "parameters"),
    )


def _encode_output_requirements(value: OutputRequirements) -> dict[str, Any]:
    return {
        "format": value.format,
        "transparent_background": value.transparent_background,
        "exact_dimensions": value.exact_dimensions,
        "minimum_width": value.minimum_width,
        "minimum_height": value.minimum_height,
    }


def _decode_output_requirements(payload: dict[str, Any]) -> OutputRequirements:
    return OutputRequirements(
        format=cast(OutputFormat, _str(payload, "format")),
        transparent_background=_bool(payload, "transparent_background"),
        exact_dimensions=_bool(payload, "exact_dimensions"),
        minimum_width=_optional_int(payload.get("minimum_width"), "minimum_width"),
        minimum_height=_optional_int(payload.get("minimum_height"), "minimum_height"),
    )


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"GENERATION_CODEC_OBJECT_REQUIRED:{key}")
    return cast(dict[str, Any], value)


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"GENERATION_CODEC_LIST_REQUIRED:{key}")
    return value


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("GENERATION_CODEC_OBJECT_REQUIRED")
    return cast(dict[str, Any], value)


def _str(payload: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"GENERATION_CODEC_STRING_REQUIRED:{key}")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("GENERATION_CODEC_OPTIONAL_STRING_INVALID")
    return value


def _int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"GENERATION_CODEC_INTEGER_REQUIRED:{key}")
    return value


def _optional_int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"GENERATION_CODEC_INTEGER_REQUIRED:{key}")
    return value


def _bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"GENERATION_CODEC_BOOLEAN_REQUIRED:{key}")
    return value


def _decimal(value: Any, key: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"GENERATION_CODEC_DECIMAL_STRING_REQUIRED:{key}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"GENERATION_CODEC_DECIMAL_INVALID:{key}") from exc
    if not parsed.is_finite():
        raise ValueError(f"GENERATION_CODEC_DECIMAL_INVALID:{key}")
    return parsed


def _plain_key(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("GENERATION_CODEC_MAP_KEY_INVALID")
    return value


def _string_value(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"GENERATION_CODEC_STRING_REQUIRED:{key}")
    return value


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("GENERATION_CODEC_NON_FINITE_FLOAT")
        return value
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {_plain_key(key): _json_value(item) for key, item in value.items()}
    raise ValueError(f"GENERATION_CODEC_JSON_VALUE_INVALID:{type(value).__name__}")
