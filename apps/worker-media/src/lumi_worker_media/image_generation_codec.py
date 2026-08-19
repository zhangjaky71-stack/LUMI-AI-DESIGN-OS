from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from lumi_image_generation.model import (
    AuthorizedReference,
    CandidateStatus,
    ConstraintSeverity,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GatewayResultStatus,
    GenerationCandidate,
    GenerationConstraint,
    GenerationJob,
    GenerationJobStatus,
    GenerationMode,
    IdentityRequirement,
    ImageGenerationSpec,
    ImageReference,
    OutputFormat,
    OutputRequirements,
    PromptBlocks,
    ProviderOutputRef,
    QualityProfile,
    ReferenceRole,
    ReferenceSource,
    Rights,
    StoredImage,
    ValidationBundle,
    ValidationFinding,
    ValidationStatus,
    VariantDecision,
)
from lumi_image_generation.ports import PendingInvocationRecord

SNAPSHOT_SCHEMA_VERSION = 1


def encode_spec(spec: ImageGenerationSpec) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
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
            "references": [_encode_image_reference(item) for item in spec.references],
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
    root = _versioned_payload(payload, "spec")
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
        references=tuple(_decode_image_reference(_object(item)) for item in raw_references),
        identity_requirements=tuple(
            _decode_identity_requirement(_object(item)) for item in raw_identity
        ),
        brand_rule_set_version=_optional_str(root.get("brand_rule_set_version")),
        constraints=tuple(_decode_constraint(_object(item)) for item in raw_constraints),
        quality_profile=cast(QualityProfile, _str(root, "quality_profile")),
        budget_limit_usd=_decimal(root.get("budget_limit_usd"), "budget_limit_usd"),
        output_requirements=_decode_output_requirements(
            _dict(root, "output_requirements")
        ),
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


def encode_job(job: GenerationJob) -> dict[str, Any]:
    return {
        "generation_id": job.generation_id,
        "organization_id": job.organization_id,
        "project_id": job.project_id,
        "task_id": job.task_id,
        "operation_id": job.operation_id,
        "semantic_hash": job.semantic_hash,
        "status": job.status,
        "prompt_hash": job.prompt_hash,
        "variant_decision": _encode_variant_decision(job.variant_decision),
        "candidates": [_encode_candidate(item) for item in job.candidates],
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error_code": job.error_code,
    }


def decode_job(payload: dict[str, Any]) -> GenerationJob:
    raw_candidates = _list(payload, "candidates")
    return GenerationJob(
        generation_id=_str(payload, "generation_id"),
        organization_id=_str(payload, "organization_id"),
        project_id=_str(payload, "project_id"),
        task_id=_str(payload, "task_id"),
        operation_id=_str(payload, "operation_id"),
        semantic_hash=_str(payload, "semantic_hash"),
        status=cast(GenerationJobStatus, _str(payload, "status")),
        prompt_hash=_str(payload, "prompt_hash"),
        variant_decision=_decode_variant_decision(_dict(payload, "variant_decision")),
        candidates=tuple(_decode_candidate(_object(item)) for item in raw_candidates),
        created_at=_str(payload, "created_at"),
        completed_at=_optional_str(payload.get("completed_at")),
        error_code=_optional_str(payload.get("error_code")),
    )


def encode_result_snapshot(
    job: GenerationJob,
    pending: dict[str, PendingInvocationRecord],
) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "job": encode_job(job),
        "pending": {key: encode_pending(value) for key, value in sorted(pending.items())},
    }


def decode_result_snapshot(
    payload: dict[str, Any],
) -> tuple[GenerationJob, dict[str, PendingInvocationRecord]]:
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("GENERATION_RESULT_SNAPSHOT_SCHEMA_UNSUPPORTED")
    job = decode_job(_dict(payload, "job"))
    raw_pending = _dict(payload, "pending")
    pending = {
        _plain_key(key): decode_pending(_object(value)) for key, value in raw_pending.items()
    }
    for key, record in pending.items():
        if key != record.candidate_id:
            raise ValueError("GENERATION_PENDING_CANDIDATE_KEY_MISMATCH")
        if record.generation_id != job.generation_id:
            raise ValueError("GENERATION_PENDING_GENERATION_MISMATCH")
    return job, pending


def encode_pending(record: PendingInvocationRecord) -> dict[str, Any]:
    return {
        "organization_id": record.organization_id,
        "generation_id": record.generation_id,
        "candidate_id": record.candidate_id,
        "variant_index": record.variant_index,
        "request": _encode_gateway_request(record.request),
        "result": _encode_gateway_result(record.result),
    }


def decode_pending(payload: dict[str, Any]) -> PendingInvocationRecord:
    return PendingInvocationRecord(
        organization_id=_str(payload, "organization_id"),
        generation_id=_str(payload, "generation_id"),
        candidate_id=_str(payload, "candidate_id"),
        variant_index=_int(payload, "variant_index"),
        request=_decode_gateway_request(_dict(payload, "request")),
        result=_decode_gateway_result(_dict(payload, "result")),
    )


def _encode_image_reference(value: ImageReference) -> dict[str, Any]:
    return {
        "asset_id": value.asset_id,
        "asset_version": value.asset_version,
        "role": value.role,
        "source": value.source,
        "note": value.note,
    }


def _decode_image_reference(payload: dict[str, Any]) -> ImageReference:
    return ImageReference(
        asset_id=_str(payload, "asset_id"),
        asset_version=_str(payload, "asset_version"),
        role=cast(ReferenceRole, _str(payload, "role")),
        source=cast(ReferenceSource, _str(payload, "source")),
        note=_optional_str(payload.get("note")),
    )


def _encode_authorized_reference(value: AuthorizedReference) -> dict[str, Any]:
    return {
        "asset_id": value.asset_id,
        "asset_version": value.asset_version,
        "role": value.role,
        "source": value.source,
        "durable_ref": value.durable_ref,
        "rights": value.rights,
        "commercial_use_allowed": value.commercial_use_allowed,
        "checksum_sha256": value.checksum_sha256,
        "mime_type": value.mime_type,
        "approval_state": value.approval_state,
    }


def _decode_authorized_reference(payload: dict[str, Any]) -> AuthorizedReference:
    return AuthorizedReference(
        asset_id=_str(payload, "asset_id"),
        asset_version=_str(payload, "asset_version"),
        role=cast(ReferenceRole, _str(payload, "role")),
        source=cast(ReferenceSource, _str(payload, "source")),
        durable_ref=_str(payload, "durable_ref"),
        rights=cast(Rights, _str(payload, "rights")),
        commercial_use_allowed=_bool(payload, "commercial_use_allowed"),
        checksum_sha256=_str(payload, "checksum_sha256"),
        mime_type=_str(payload, "mime_type"),
        approval_state=_optional_str(payload.get("approval_state")),
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


def _encode_prompt(value: PromptBlocks) -> dict[str, Any]:
    return {
        "objective": value.objective,
        "content": value.content,
        "visual_direction": value.visual_direction,
        "brand_constraints": list(value.brand_constraints),
        "identity_requirements": list(value.identity_requirements),
        "negative_constraints": list(value.negative_constraints),
        "output_dimensions": value.output_dimensions,
        "template_version": value.template_version,
    }


def _decode_prompt(payload: dict[str, Any]) -> PromptBlocks:
    return PromptBlocks(
        objective=_str(payload, "objective"),
        content=_str(payload, "content"),
        visual_direction=_str(payload, "visual_direction", allow_empty=True),
        brand_constraints=_str_tuple(payload, "brand_constraints"),
        identity_requirements=_str_tuple(payload, "identity_requirements"),
        negative_constraints=_str_tuple(payload, "negative_constraints"),
        output_dimensions=_str(payload, "output_dimensions"),
        template_version=_str(payload, "template_version"),
    )


def _encode_variant_decision(value: VariantDecision) -> dict[str, Any]:
    return {
        "requested_count": value.requested_count,
        "selected_count": value.selected_count,
        "estimated_cost_per_variant_usd": format(
            value.estimated_cost_per_variant_usd,
            "f",
        ),
        "estimated_total_usd": format(value.estimated_total_usd, "f"),
        "reason_codes": list(value.reason_codes),
    }


def _decode_variant_decision(payload: dict[str, Any]) -> VariantDecision:
    return VariantDecision(
        requested_count=_int(payload, "requested_count"),
        selected_count=_int(payload, "selected_count"),
        estimated_cost_per_variant_usd=_decimal(
            payload.get("estimated_cost_per_variant_usd"),
            "estimated_cost_per_variant_usd",
        ),
        estimated_total_usd=_decimal(
            payload.get("estimated_total_usd"),
            "estimated_total_usd",
        ),
        reason_codes=_str_tuple(payload, "reason_codes"),
    )


def _encode_candidate(value: GenerationCandidate) -> dict[str, Any]:
    return {
        "candidate_id": value.candidate_id,
        "generation_id": value.generation_id,
        "variant_index": value.variant_index,
        "status": value.status,
        "provider": value.provider,
        "model": value.model,
        "provider_request_id": value.provider_request_id,
        "provider_output_ref": value.provider_output_ref,
        "stored_image": (
            _encode_stored_image(value.stored_image) if value.stored_image is not None else None
        ),
        "artifact_id": value.artifact_id,
        "artifact_version_id": value.artifact_version_id,
        "validation": (
            _encode_validation_bundle(value.validation) if value.validation is not None else None
        ),
        "provenance_snapshot_id": value.provenance_snapshot_id,
        "error_code": value.error_code,
    }


def _decode_candidate(payload: dict[str, Any]) -> GenerationCandidate:
    raw_stored = payload.get("stored_image")
    raw_validation = payload.get("validation")
    return GenerationCandidate(
        candidate_id=_str(payload, "candidate_id"),
        generation_id=_str(payload, "generation_id"),
        variant_index=_int(payload, "variant_index"),
        status=cast(CandidateStatus, _str(payload, "status")),
        provider=_optional_str(payload.get("provider")),
        model=_optional_str(payload.get("model")),
        provider_request_id=_optional_str(payload.get("provider_request_id")),
        provider_output_ref=_optional_str(payload.get("provider_output_ref")),
        stored_image=(
            _decode_stored_image(_object(raw_stored)) if raw_stored is not None else None
        ),
        artifact_id=_optional_str(payload.get("artifact_id")),
        artifact_version_id=_optional_str(payload.get("artifact_version_id")),
        validation=(
            _decode_validation_bundle(_object(raw_validation))
            if raw_validation is not None
            else None
        ),
        provenance_snapshot_id=_optional_str(payload.get("provenance_snapshot_id")),
        error_code=_optional_str(payload.get("error_code")),
    )


def _encode_stored_image(value: StoredImage) -> dict[str, Any]:
    return {
        "storage_key": value.storage_key,
        "mime_type": value.mime_type,
        "width": value.width,
        "height": value.height,
        "size_bytes": value.size_bytes,
        "checksum_sha256": value.checksum_sha256,
    }


def _decode_stored_image(payload: dict[str, Any]) -> StoredImage:
    return StoredImage(
        storage_key=_str(payload, "storage_key"),
        mime_type=_str(payload, "mime_type"),
        width=_int(payload, "width"),
        height=_int(payload, "height"),
        size_bytes=_int(payload, "size_bytes"),
        checksum_sha256=_str(payload, "checksum_sha256"),
    )


def _encode_validation_bundle(value: ValidationBundle) -> dict[str, Any]:
    return {
        "findings": [_encode_validation_finding(item) for item in value.findings],
        "identity_validation_snapshot_id": value.identity_validation_snapshot_id,
        "brand_validation_snapshot_id": value.brand_validation_snapshot_id,
    }


def _decode_validation_bundle(payload: dict[str, Any]) -> ValidationBundle:
    return ValidationBundle(
        findings=tuple(
            _decode_validation_finding(_object(item)) for item in _list(payload, "findings")
        ),
        identity_validation_snapshot_id=_optional_str(
            payload.get("identity_validation_snapshot_id")
        ),
        brand_validation_snapshot_id=_optional_str(
            payload.get("brand_validation_snapshot_id")
        ),
    )


def _encode_validation_finding(value: ValidationFinding) -> dict[str, Any]:
    return {
        "validator": value.validator,
        "status": value.status,
        "severity": value.severity,
        "reason_code": value.reason_code,
        "score": value.score,
        "threshold": value.threshold,
        "evidence_refs": list(value.evidence_refs),
    }


def _decode_validation_finding(payload: dict[str, Any]) -> ValidationFinding:
    return ValidationFinding(
        validator=_str(payload, "validator"),
        status=cast(ValidationStatus, _str(payload, "status")),
        severity=cast(ConstraintSeverity, _str(payload, "severity")),
        reason_code=_str(payload, "reason_code"),
        score=_optional_float(payload.get("score"), "score"),
        threshold=_optional_float(payload.get("threshold"), "threshold"),
        evidence_refs=_str_tuple(payload, "evidence_refs"),
    )


def _encode_gateway_request(value: GatewayGenerationRequest) -> dict[str, Any]:
    return {
        "organization_id": value.organization_id,
        "project_id": value.project_id,
        "task_id": value.task_id,
        "root_operation_id": value.root_operation_id,
        "variant_operation_id": value.variant_operation_id,
        "generation_id": value.generation_id,
        "variant_index": value.variant_index,
        "mode": value.mode,
        "prompt": _encode_prompt(value.prompt),
        "references": [_encode_authorized_reference(item) for item in value.references],
        "target_width": value.target_width,
        "target_height": value.target_height,
        "quality_profile": value.quality_profile,
        "budget_limit_usd": format(value.budget_limit_usd, "f"),
        "constraints": [_encode_constraint(item) for item in value.constraints],
        "output_requirements": _encode_output_requirements(value.output_requirements),
        "seed": value.seed,
        "agent_run_id": value.agent_run_id,
    }


def _decode_gateway_request(payload: dict[str, Any]) -> GatewayGenerationRequest:
    return GatewayGenerationRequest(
        organization_id=_str(payload, "organization_id"),
        project_id=_str(payload, "project_id"),
        task_id=_str(payload, "task_id"),
        root_operation_id=_str(payload, "root_operation_id"),
        variant_operation_id=_str(payload, "variant_operation_id"),
        generation_id=_str(payload, "generation_id"),
        variant_index=_int(payload, "variant_index"),
        mode=cast(GenerationMode, _str(payload, "mode")),
        prompt=_decode_prompt(_dict(payload, "prompt")),
        references=tuple(
            _decode_authorized_reference(_object(item))
            for item in _list(payload, "references")
        ),
        target_width=_int(payload, "target_width"),
        target_height=_int(payload, "target_height"),
        quality_profile=cast(QualityProfile, _str(payload, "quality_profile")),
        budget_limit_usd=_decimal(payload.get("budget_limit_usd"), "budget_limit_usd"),
        constraints=tuple(
            _decode_constraint(_object(item)) for item in _list(payload, "constraints")
        ),
        output_requirements=_decode_output_requirements(
            _dict(payload, "output_requirements")
        ),
        seed=_optional_int(payload.get("seed"), "seed"),
        agent_run_id=_optional_str(payload.get("agent_run_id")),
    )


def _encode_gateway_result(value: GatewayGenerationResult) -> dict[str, Any]:
    return {
        "status": value.status,
        "provider": value.provider,
        "model": value.model,
        "model_revision": value.model_revision,
        "provider_request_id": value.provider_request_id,
        "outputs": [
            {"ref": item.ref, "mime_type": item.mime_type} for item in value.outputs
        ],
        "cost_usd": format(value.cost_usd, "f") if value.cost_usd is not None else None,
        "cost_confidence": value.cost_confidence,
        "pricing_snapshot_id": value.pricing_snapshot_id,
        "routing_reason_codes": list(value.routing_reason_codes),
        "safety_metadata": _json_value(dict(value.safety_metadata)),
        "finish_reason": value.finish_reason,
        "seed": value.seed,
    }


def _decode_gateway_result(payload: dict[str, Any]) -> GatewayGenerationResult:
    return GatewayGenerationResult(
        status=cast(GatewayResultStatus, _str(payload, "status")),
        provider=_str(payload, "provider"),
        model=_str(payload, "model"),
        model_revision=_optional_str(payload.get("model_revision")),
        provider_request_id=_optional_str(payload.get("provider_request_id")),
        outputs=tuple(
            ProviderOutputRef(
                ref=_str(_object(item), "ref"),
                mime_type=_optional_str(_object(item).get("mime_type")),
            )
            for item in _list(payload, "outputs")
        ),
        cost_usd=_optional_decimal(payload.get("cost_usd"), "cost_usd"),
        cost_confidence=_str(payload, "cost_confidence"),
        pricing_snapshot_id=_optional_str(payload.get("pricing_snapshot_id")),
        routing_reason_codes=_str_tuple(payload, "routing_reason_codes"),
        safety_metadata=_dict(payload, "safety_metadata"),
        finish_reason=_optional_str(payload.get("finish_reason")),
        seed=_optional_int(payload.get("seed"), "seed"),
    )


def _versioned_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("GENERATION_SPEC_SNAPSHOT_SCHEMA_UNSUPPORTED")
    return _dict(payload, key)


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("GENERATION_SNAPSHOT_OBJECT_INVALID")
    return value


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _object(payload.get(key))


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"GENERATION_SNAPSHOT_{key.upper()}_LIST_INVALID")
    return value


def _str(payload: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"GENERATION_SNAPSHOT_{key.upper()}_STRING_INVALID")
    if "\x00" in value:
        raise ValueError(f"GENERATION_SNAPSHOT_{key.upper()}_STRING_INVALID")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("GENERATION_SNAPSHOT_OPTIONAL_STRING_INVALID")
    return value


def _string_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError(f"GENERATION_SNAPSHOT_STRING_INVALID:{label}")
    return value


def _plain_key(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("GENERATION_SNAPSHOT_KEY_INVALID")
    return value


def _int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"GENERATION_SNAPSHOT_{key.upper()}_INT_INVALID")
    return value


def _optional_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"GENERATION_SNAPSHOT_INT_INVALID:{label}")
    return value


def _bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"GENERATION_SNAPSHOT_{key.upper()}_BOOL_INVALID")
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"GENERATION_SNAPSHOT_DECIMAL_INVALID:{label}")
    try:
        decoded = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"GENERATION_SNAPSHOT_DECIMAL_INVALID:{label}") from exc
    if not decoded.is_finite():
        raise ValueError(f"GENERATION_SNAPSHOT_DECIMAL_INVALID:{label}")
    return decoded


def _optional_decimal(value: Any, label: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, label)


def _optional_float(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"GENERATION_SNAPSHOT_FLOAT_INVALID:{label}")
    decoded = float(value)
    if not math.isfinite(decoded):
        raise ValueError(f"GENERATION_SNAPSHOT_FLOAT_INVALID:{label}")
    return decoded


def _str_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    return tuple(_string_value(value, key) for value in _list(payload, key))


def _json_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 24:
        raise ValueError("GENERATION_SNAPSHOT_JSON_TOO_DEEP")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("GENERATION_SNAPSHOT_JSON_NON_FINITE")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("GENERATION_SNAPSHOT_JSON_NON_FINITE")
        return format(value, "f")
    if isinstance(value, (list, tuple)):
        return [_json_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("GENERATION_SNAPSHOT_JSON_KEY_INVALID")
        return {
            key: _json_value(item, depth=depth + 1)
            for key, item in sorted(value.items())
        }
    raise ValueError(f"GENERATION_SNAPSHOT_JSON_TYPE_INVALID:{type(value).__name__}")
