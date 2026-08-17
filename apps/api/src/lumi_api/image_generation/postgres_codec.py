from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from lumi_image_generation import (
    AuthorizedReference, CandidateStatus, ConstraintSeverity, GatewayRequest, GatewayResult,
    GatewayStatus, GenerationCandidate, GenerationConstraint, GenerationJob, GenerationMode,
    ImageGenerationSpec, ImageReference, IdentityRequirement, JobStatus, OutputFormat,
    OutputRequirements, PromptBlocks, ProviderOutputRef, QualityProfile, ReferenceRole,
    ReferenceSource, StoredImage, ValidationBundle, ValidationFinding, ValidationStatus,
    VariantDecision,
)

def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value

def _dump(value: Any) -> str:
    return json.dumps(_json_value(asdict(value)), sort_keys=True, separators=(",", ":"))

def _constraint(value: dict[str, Any]) -> GenerationConstraint:
    return GenerationConstraint(
        value["constraint_id"],
        value["constraint_type"],
        ConstraintSeverity(value["severity"]),
        value["snapshot_hash"],
        value.get("parameters") or {},
    )

def _reference(value: dict[str, Any]) -> ImageReference:
    return ImageReference(
        UUID(value["asset_id"]),
        value["asset_version"],
        ReferenceRole(value["role"]),
        ReferenceSource(value["source"]),
        value.get("note"),
    )

def _authorized(value: dict[str, Any]) -> AuthorizedReference:
    return AuthorizedReference(
        UUID(value["asset_id"]),
        value["asset_version"],
        ReferenceRole(value["role"]),
        ReferenceSource(value["source"]),
        value["durable_ref"],
        value["rights_level"],
        bool(value["commercial_use"]),
        value["checksum_sha256"],
        value["mime_type"],
        value.get("approval_state"),
        tuple(value.get("evidence_refs") or ()),
    )

def _output_requirements(value: dict[str, Any]) -> OutputRequirements:
    return OutputRequirements(
        OutputFormat(value["format"]),
        bool(value["transparent_background"]),
        bool(value["exact_dimensions"]),
        value.get("minimum_width"),
        value.get("minimum_height"),
    )

def _spec(payload: dict[str, Any]) -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=UUID(payload["organization_id"]),
        project_id=UUID(payload["project_id"]),
        task_id=UUID(payload["task_id"]),
        operation_id=UUID(payload["operation_id"]),
        purpose=payload["purpose"],
        mode=GenerationMode(payload["mode"]),
        prompt_compilation_ref=payload["prompt_compilation_ref"],
        objective=payload["objective"],
        content=payload["content"],
        visual_direction=payload["visual_direction"],
        aspect_ratio=payload["aspect_ratio"],
        target_width=int(payload["target_width"]),
        target_height=int(payload["target_height"]),
        variant_count=int(payload["variant_count"]),
        references=tuple(_reference(item) for item in payload.get("references") or ()),
        identity_requirements=tuple(
            IdentityRequirement(
                UUID(item["identity_id"]),
                item["reference_set_version"],
                ConstraintSeverity(item["severity"]),
                item["scenario"],
            )
            for item in payload.get("identity_requirements") or ()
        ),
        brand_rule_set_version=payload.get("brand_rule_set_version"),
        constraints=tuple(_constraint(item) for item in payload.get("constraints") or ()),
        quality_profile=QualityProfile(payload["quality_profile"]),
        budget_limit_usd=Decimal(payload["budget_limit_usd"]),
        output_requirements=_output_requirements(payload["output_requirements"]),
        code_git_sha=payload["code_git_sha"],
        agent_run_id=UUID(payload["agent_run_id"]) if payload.get("agent_run_id") else None,
        agent_version=payload.get("agent_version"),
        recipe_version=payload.get("recipe_version"),
        skill_versions=payload.get("skill_versions") or {},
        seed=payload.get("seed"),
        user_intent_ref=payload.get("user_intent_ref"),
        user_use_declaration=payload.get("user_use_declaration"),
    )

def _prompt(value: dict[str, Any]) -> PromptBlocks:
    return PromptBlocks(
        value["objective"],
        value["content"],
        value["visual_direction"],
        tuple(value.get("brand_constraints") or ()),
        tuple(value.get("identity_requirements") or ()),
        tuple(value.get("negative_constraints") or ()),
        value["output_dimensions"],
        value["template_version"],
    )

def _validation(value: dict[str, Any] | None) -> ValidationBundle | None:
    if value is None:
        return None
    return ValidationBundle(
        findings=tuple(
            ValidationFinding(
                item["validator"],
                ValidationStatus(item["status"]),
                ConstraintSeverity(item["severity"]),
                item["reason_code"],
                item.get("score"),
                item.get("threshold"),
                tuple(item.get("evidence_refs") or ()),
            )
            for item in value.get("findings") or ()
        ),
        identity_validation_snapshot_id=value.get("identity_validation_snapshot_id"),
        brand_validation_snapshot_id=value.get("brand_validation_snapshot_id"),
    )

def _stored(value: dict[str, Any] | None) -> StoredImage | None:
    if value is None:
        return None
    return StoredImage(
        value["bucket"],
        value["storage_key"],
        value["mime_type"],
        int(value["width"]),
        int(value["height"]),
        int(value["size_bytes"]),
        value["checksum_sha256"],
    )

def _candidate(value: dict[str, Any]) -> GenerationCandidate:
    return GenerationCandidate(
        candidate_id=UUID(value["candidate_id"]),
        generation_id=UUID(value["generation_id"]),
        variant_index=int(value["variant_index"]),
        variant_operation_id=UUID(value["variant_operation_id"]),
        status=CandidateStatus(value["status"]),
        provider=value.get("provider"),
        model=value.get("model"),
        provider_request_id=value.get("provider_request_id"),
        model_revision=value.get("model_revision"),
        registry_snapshot_id=value.get("registry_snapshot_id"),
        stored_image=_stored(value.get("stored_image")),
        artifact_id=UUID(value["artifact_id"]) if value.get("artifact_id") else None,
        artifact_version_id=(
            UUID(value["artifact_version_id"]) if value.get("artifact_version_id") else None
        ),
        validation=_validation(value.get("validation")),
        provenance_snapshot_id=value.get("provenance_snapshot_id"),
        cost_usd=Decimal(value["cost_usd"]) if value.get("cost_usd") is not None else None,
        cost_confidence=value.get("cost_confidence"),
        pricing_snapshot_id=value.get("pricing_snapshot_id"),
        routing_reason_codes=tuple(value.get("routing_reason_codes") or ()),
        error_code=value.get("error_code"),
    )

def _job(payload: dict[str, Any]) -> GenerationJob:
    decision = payload["variant_decision"]
    return GenerationJob(
        generation_id=UUID(payload["generation_id"]),
        organization_id=UUID(payload["organization_id"]),
        project_id=UUID(payload["project_id"]),
        task_id=UUID(payload["task_id"]),
        operation_id=UUID(payload["operation_id"]),
        semantic_hash=payload["semantic_hash"],
        status=JobStatus(payload["status"]),
        prompt_hash=payload["prompt_hash"],
        prompt=_prompt(payload["prompt"]),
        authorized_references=tuple(
            _authorized(item) for item in payload.get("authorized_references") or ()
        ),
        variant_decision=VariantDecision(
            int(decision["requested_count"]),
            int(decision["selected_count"]),
            Decimal(decision["estimated_cost_per_variant_usd"]),
            Decimal(decision["estimated_total_usd"]),
            tuple(decision.get("reason_codes") or ()),
        ),
        candidates=tuple(_candidate(item) for item in payload.get("candidates") or ()),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        completed_at=payload.get("completed_at"),
        error_code=payload.get("error_code"),
    )

def _gateway_request(payload: dict[str, Any]) -> GatewayRequest:
    return GatewayRequest(
        request_id=UUID(payload["request_id"]),
        organization_id=UUID(payload["organization_id"]),
        project_id=UUID(payload["project_id"]),
        task_id=UUID(payload["task_id"]),
        root_operation_id=UUID(payload["root_operation_id"]),
        variant_operation_id=UUID(payload["variant_operation_id"]),
        generation_id=UUID(payload["generation_id"]),
        variant_index=int(payload["variant_index"]),
        mode=GenerationMode(payload["mode"]),
        prompt=_prompt(payload["prompt"]),
        references=tuple(_authorized(item) for item in payload.get("references") or ()),
        target_width=int(payload["target_width"]),
        target_height=int(payload["target_height"]),
        quality_profile=QualityProfile(payload["quality_profile"]),
        budget_limit_usd=Decimal(payload["budget_limit_usd"]),
        constraints=tuple(_constraint(item) for item in payload.get("constraints") or ()),
        output_requirements=_output_requirements(payload["output_requirements"]),
        seed=payload.get("seed"),
        agent_run_id=UUID(payload["agent_run_id"]) if payload.get("agent_run_id") else None,
    )

def _gateway_result(payload: dict[str, Any]) -> GatewayResult:
    return GatewayResult(
        status=GatewayStatus(payload["status"]),
        provider=payload["provider"],
        model=payload["model"],
        outputs=tuple(
            ProviderOutputRef(item["ref"], item.get("mime_type"))
            for item in payload.get("outputs") or ()
        ),
        provider_request_id=payload.get("provider_request_id"),
        model_revision=payload.get("model_revision"),
        registry_snapshot_id=payload.get("registry_snapshot_id"),
        cost_usd=Decimal(payload["cost_usd"]) if payload.get("cost_usd") is not None else None,
        cost_confidence=payload.get("cost_confidence", "unknown"),
        pricing_snapshot_id=payload.get("pricing_snapshot_id"),
        routing_reason_codes=tuple(payload.get("routing_reason_codes") or ()),
        safety_metadata=payload.get("safety_metadata") or {},
        finish_reason=payload.get("finish_reason"),
        seed=payload.get("seed"),
    )
