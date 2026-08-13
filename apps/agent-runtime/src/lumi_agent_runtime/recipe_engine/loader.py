from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .contracts import (
    ApprovalPolicy,
    JoinPolicy,
    LoopPolicy,
    ParallelPolicy,
    QualityGatePolicy,
    RecipeDefinition,
    RecipeReleaseManifest,
    RecipeReleaseRecord,
    RecipeReleaseStatus,
    RecipeStep,
    StepType,
)
from .errors import RecipeDefinitionInvalidError, RecipeSecurityError
from .expression import validate_expression

_FORBIDDEN_KEYS = frozenset(
    {
        "script",
        "command",
        "shell",
        "sql",
        "raw_url",
        "api_key",
        "apikey",
        "provider_key",
        "secret",
        "access_token",
        "private_key",
    }
)
_URL = re.compile(r"(?i)^https?://")
_SQL = re.compile(r"(?is)^\s*(select|insert|update|delete|drop|alter|create|grant|revoke)\s+")


def load_recipe(version_dir: Path) -> RecipeDefinition:
    payload = _object(
        _read_json(version_dir / "recipe.yaml"),
        "RECIPE_DEFINITION_OBJECT_REQUIRED",
    )
    _security_scan(payload, path="$")
    if payload.get("id") != version_dir.parent.name or payload.get("version") != version_dir.name:
        raise RecipeDefinitionInvalidError("Recipe path must match id/version")
    try:
        definition = RecipeDefinition(
            recipe_id=_string(payload.get("id"), "RECIPE_ID_REQUIRED"),
            version=_string(payload.get("version"), "RECIPE_VERSION_REQUIRED"),
            inputs=tuple(_strings(payload.get("inputs"), "RECIPE_INPUTS_REQUIRED")),
            steps=tuple(
                _step(_object(item, "RECIPE_STEP_OBJECT_REQUIRED"))
                for item in _list(payload.get("steps"), "RECIPE_STEPS_REQUIRED")
            ),
            outputs={
                str(key): _string(value, "RECIPE_OUTPUT_BINDING_INVALID")
                for key, value in _object(
                    payload.get("outputs", {}), "RECIPE_OUTPUTS_INVALID"
                ).items()
            },
            budget_limit_usd=_optional_decimal_string(payload.get("budget_limit_usd")),
            metadata=dict(
                _object(payload.get("metadata", {}), "RECIPE_METADATA_INVALID")
            ),
        )
    except (TypeError, ValueError) as exc:
        raise RecipeDefinitionInvalidError(str(exc)) from exc
    return definition


def load_recipes(root: Path) -> tuple[RecipeDefinition, ...]:
    rows: list[RecipeDefinition] = []
    for recipe_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        for version_dir in sorted(path for path in recipe_dir.iterdir() if path.is_dir()):
            if (version_dir / "recipe.yaml").exists():
                rows.append(load_recipe(version_dir))
    return tuple(rows)


def load_release_manifest(path: Path) -> RecipeReleaseManifest:
    payload = _object(_read_json(path), "RECIPE_RELEASE_MANIFEST_INVALID")
    releases = tuple(
        RecipeReleaseRecord(
            recipe_id=_string(row.get("id"), "RECIPE_RELEASE_ID_REQUIRED"),
            version=_string(row.get("version"), "RECIPE_RELEASE_VERSION_REQUIRED"),
            status=RecipeReleaseStatus(
                _string(row.get("status"), "RECIPE_RELEASE_STATUS_REQUIRED")
            ),
            eval_profile=_string(
                row.get("eval_profile"), "RECIPE_RELEASE_EVAL_PROFILE_REQUIRED"
            ),
            eval_status=(
                row.get("eval_status")
                if isinstance(row.get("eval_status"), str)
                else None
            ),
            eval_evidence=(
                row.get("eval_evidence")
                if isinstance(row.get("eval_evidence"), str)
                else None
            ),
        )
        for row in (
            _object(item, "RECIPE_RELEASE_RECORD_INVALID")
            for item in _list(payload.get("releases"), "RECIPE_RELEASES_REQUIRED")
        )
    )
    aliases = {
        str(recipe_id): {
            str(alias): _string(version, "RECIPE_ALIAS_VERSION_INVALID")
            for alias, version in _object(values, "RECIPE_ALIAS_MAP_INVALID").items()
        }
        for recipe_id, values in _object(
            payload.get("aliases", {}), "RECIPE_ALIASES_INVALID"
        ).items()
    }
    return RecipeReleaseManifest(
        schema=_string(payload.get("schema"), "RECIPE_RELEASE_SCHEMA_REQUIRED"),
        revision=int(payload.get("revision", 0)),
        releases=releases,
        aliases=aliases,
    )


def _step(payload: dict[str, Any]) -> RecipeStep:
    try:
        step_type = StepType(_string(payload.get("type"), "RECIPE_STEP_TYPE_REQUIRED").upper())
    except ValueError as exc:
        raise RecipeDefinitionInvalidError("RECIPE_STEP_TYPE_UNSUPPORTED") from exc
    condition = _optional_string(payload.get("if"))
    if condition is not None:
        validate_expression(condition)
    loop = _loop(payload.get("loop"))
    if loop is not None and loop.stop_condition is not None:
        validate_expression(loop.stop_condition)
    children = tuple(
        _step(_object(item, "RECIPE_PARALLEL_CHILD_INVALID"))
        for item in _list(payload.get("children", []), "RECIPE_PARALLEL_CHILDREN_INVALID")
    )
    template_payload = payload.get("template")
    template = (
        _step(_object(template_payload, "RECIPE_FOREACH_TEMPLATE_INVALID"))
        if template_payload is not None
        else None
    )
    step = RecipeStep(
        step_id=_string(payload.get("id"), "RECIPE_STEP_ID_REQUIRED"),
        step_type=step_type,
        depends_on=tuple(
            _strings(payload.get("depends_on", []), "RECIPE_DEPENDENCIES_INVALID")
        ),
        input_bindings={
            str(key): _string(value, "RECIPE_INPUT_BINDING_INVALID")
            for key, value in _object(
                payload.get("input", {}), "RECIPE_INPUT_BINDINGS_INVALID"
            ).items()
        },
        output_schema=_string(
            payload.get("output_schema", "GenericTaskOutput"),
            "RECIPE_OUTPUT_SCHEMA_INVALID",
        ),
        condition=condition,
        budget_limit_usd=_optional_decimal_string(payload.get("budget_limit_usd")),
        agent_ref=_optional_string(payload.get("agent")),
        skill_refs=tuple(
            _strings(payload.get("skills", []), "RECIPE_SKILLS_INVALID")
        ),
        service_key=_optional_string(payload.get("service")),
        media_operation=_optional_string(payload.get("operation")),
        recipe_ref=_optional_string(payload.get("recipe")),
        parallel=_parallel(payload.get("parallel")),
        children=children,
        foreach_count=(
            int(payload["count"])
            if "count" in payload and isinstance(payload["count"], int)
            else None
        ),
        template=template,
        approval=_approval(payload.get("approval")),
        quality_gate=_quality_gate(payload.get("quality_gate")),
        loop=loop,
        metadata=dict(
            _object(payload.get("metadata", {}), "RECIPE_STEP_METADATA_INVALID")
        ),
    )
    _validate_step_shape(step)
    return step


def _validate_step_shape(step: RecipeStep) -> None:
    if step.step_type == StepType.AGENT:
        if step.agent_ref is None:
            raise RecipeDefinitionInvalidError("RECIPE_AGENT_REF_REQUIRED")
    elif step.skill_refs:
        raise RecipeDefinitionInvalidError("RECIPE_SKILLS_ONLY_ALLOWED_ON_AGENT")
    if step.step_type in {StepType.DETERMINISTIC, StepType.FINALIZE}:
        if step.service_key is None:
            raise RecipeDefinitionInvalidError("RECIPE_SERVICE_KEY_REQUIRED")
    if step.step_type == StepType.MEDIA_JOB and step.media_operation is None:
        raise RecipeDefinitionInvalidError("RECIPE_MEDIA_OPERATION_REQUIRED")
    if step.step_type == StepType.SUBRECIPE and step.recipe_ref is None:
        raise RecipeDefinitionInvalidError("RECIPE_SUBRECIPE_REF_REQUIRED")
    if step.step_type == StepType.APPROVAL and step.approval is None:
        raise RecipeDefinitionInvalidError("RECIPE_APPROVAL_POLICY_REQUIRED")
    if step.step_type == StepType.QUALITY_GATE and step.quality_gate is None:
        raise RecipeDefinitionInvalidError("RECIPE_QUALITY_POLICY_REQUIRED")
    if step.step_type == StepType.PARALLEL:
        if step.parallel is None or not step.children:
            raise RecipeDefinitionInvalidError("RECIPE_PARALLEL_POLICY_CHILDREN_REQUIRED")
        if step.parallel.max_parallel > len(step.children):
            raise RecipeDefinitionInvalidError("RECIPE_PARALLEL_LIMIT_EXCEEDS_CHILDREN")
        if step.parallel.budget_split and len(step.parallel.budget_split) != len(step.children):
            raise RecipeDefinitionInvalidError("RECIPE_PARALLEL_BUDGET_SPLIT_COUNT_INVALID")
    elif step.children or step.parallel is not None:
        raise RecipeDefinitionInvalidError("RECIPE_PARALLEL_FIELDS_FORBIDDEN")
    if step.step_type == StepType.FOREACH:
        if step.foreach_count is None or not 1 <= step.foreach_count <= 8 or step.template is None:
            raise RecipeDefinitionInvalidError("RECIPE_FOREACH_BOUNDED_TEMPLATE_REQUIRED")
    elif step.foreach_count is not None or step.template is not None:
        raise RecipeDefinitionInvalidError("RECIPE_FOREACH_FIELDS_FORBIDDEN")
    if step.step_type in {StepType.PARALLEL, StepType.FOREACH} and step.loop is not None:
        raise RecipeDefinitionInvalidError("RECIPE_CONTAINER_LOOP_FORBIDDEN")


def _parallel(value: Any) -> ParallelPolicy | None:
    if value is None:
        return None
    raw = _object(value, "RECIPE_PARALLEL_POLICY_INVALID")
    return ParallelPolicy(
        max_parallel=int(raw.get("max_parallel", 0)),
        join_policy=JoinPolicy(
            _string(raw.get("join_policy", "ALL"), "RECIPE_JOIN_POLICY_INVALID").upper()
        ),
        min_success=(
            int(raw["min_success"])
            if isinstance(raw.get("min_success"), int)
            else None
        ),
        budget_limit_usd=_optional_decimal_string(raw.get("budget_limit_usd")),
        budget_split=tuple(
            _decimal_strings(raw.get("budget_split", []), "RECIPE_BUDGET_SPLIT_INVALID")
        ),
    )


def _approval(value: Any) -> ApprovalPolicy | None:
    if value is None:
        return None
    raw = _object(value, "RECIPE_APPROVAL_POLICY_INVALID")
    return ApprovalPolicy(
        prompt_summary=_string(raw.get("prompt_summary"), "RECIPE_APPROVAL_PROMPT_REQUIRED"),
        allowed_actions=tuple(
            _strings(raw.get("allowed_actions"), "RECIPE_APPROVAL_ACTIONS_REQUIRED")
        ),
        artifact_refs=tuple(
            _strings(raw.get("artifact_refs", []), "RECIPE_APPROVAL_ARTIFACT_REFS_INVALID")
        ),
        option_refs=tuple(
            _strings(raw.get("option_refs", []), "RECIPE_APPROVAL_OPTION_REFS_INVALID")
        ),
        expiry_seconds=(
            int(raw["expiry_seconds"])
            if isinstance(raw.get("expiry_seconds"), int)
            else None
        ),
        resume_mapping={
            str(key): _string(mapped, "RECIPE_APPROVAL_RESUME_MAPPING_INVALID")
            for key, mapped in _object(
                raw.get("resume_mapping", {}), "RECIPE_APPROVAL_RESUME_MAPPING_INVALID"
            ).items()
        },
    )


def _quality_gate(value: Any) -> QualityGatePolicy | None:
    if value is None:
        return None
    raw = _object(value, "RECIPE_QUALITY_POLICY_INVALID")
    thresholds_raw = _object(raw.get("thresholds", {}), "RECIPE_QUALITY_THRESHOLDS_INVALID")
    thresholds: dict[str, float | int] = {}
    for key, threshold in thresholds_raw.items():
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise RecipeDefinitionInvalidError("RECIPE_QUALITY_THRESHOLD_INVALID")
        thresholds[str(key)] = threshold
    return QualityGatePolicy(
        metrics=tuple(_strings(raw.get("metrics"), "RECIPE_QUALITY_METRICS_REQUIRED")),
        thresholds=thresholds,
        repair_recipe=_optional_string(raw.get("repair_recipe")),
        max_repair_iterations=int(raw.get("max_repair_iterations", 0)),
    )


def _loop(value: Any) -> LoopPolicy | None:
    if value is None:
        return None
    raw = _object(value, "RECIPE_LOOP_POLICY_INVALID")
    return LoopPolicy(
        max_iterations=int(raw.get("max_iterations", 0)),
        budget_limit_usd=_optional_decimal_string(raw.get("budget_limit_usd")),
        stop_condition=_optional_string(raw.get("stop_condition")),
    )


def _security_scan(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise RecipeSecurityError(f"RECIPE_AUTHORITY_FIELD_FORBIDDEN:{path}.{key}")
            _security_scan(child, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _security_scan(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        if _URL.match(value):
            raise RecipeSecurityError(f"RECIPE_RAW_URL_FORBIDDEN:{path}")
        if _SQL.match(value):
            raise RecipeSecurityError(f"RECIPE_RAW_SQL_FORBIDDEN:{path}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecipeDefinitionInvalidError(f"invalid JSON-compatible YAML: {path}") from exc


def _object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecipeDefinitionInvalidError(code)
    return value


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise RecipeDefinitionInvalidError(code)
    return value


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise RecipeDefinitionInvalidError(code)
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return _string(value, "RECIPE_STRING_INVALID")


def _strings(value: Any, code: str) -> list[str]:
    rows = _list(value, code)
    if not all(isinstance(item, str) and item for item in rows):
        raise RecipeDefinitionInvalidError(code)
    return rows


def _optional_decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise RecipeDefinitionInvalidError("RECIPE_DECIMAL_STRING_REQUIRED")
    return str(value)


def _decimal_strings(value: Any, code: str) -> list[str]:
    rows = _list(value, code)
    result: list[str] = []
    for item in rows:
        parsed = _optional_decimal_string(item)
        if parsed is None:
            raise RecipeDefinitionInvalidError(code)
        result.append(parsed)
    return result
