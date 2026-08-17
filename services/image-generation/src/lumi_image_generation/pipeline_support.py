from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid5

from .model import (
    CandidateStatus, ConstraintSeverity, GatewayRequest, GatewayResult, GenerationCandidate,
    GenerationJob, GenerationMode, ImageGenerationSpec, ValidationBundle, ValidationFinding,
    ValidationStatus,
)

_REFERENCE_REQUIRED = {
    GenerationMode.REFERENCE_TO_IMAGE,
    GenerationMode.PRODUCT_SCENE,
    GenerationMode.STYLE_REFERENCE,
}
_GENERATION_NAMESPACE = UUID("3c4c1d9e-4ec2-4fe5-96ee-c39fc2978884")


class ImageGenerationPipelineError(ValueError):
    pass

def _generation_id(spec: ImageGenerationSpec) -> UUID:
    return uuid5(
        _GENERATION_NAMESPACE,
        f"{spec.organization_id}:{spec.operation_id}:{spec.semantic_hash}",
    )

def _variant_operation_id(operation_id: UUID, index: int) -> UUID:
    return uuid5(operation_id, f"image-generation-variant:{index}")

def _candidate_id(generation_id: UUID, index: int) -> UUID:
    return uuid5(generation_id, f"candidate:{index}")

def _request_id(variant_operation_id: UUID) -> UUID:
    return uuid5(variant_operation_id, "node22-model-request")

def _validate_reference_roles(spec: ImageGenerationSpec) -> None:
    if spec.mode in _REFERENCE_REQUIRED and not spec.references:
        raise ImageGenerationPipelineError("GENERATION_MODE_REQUIRES_REFERENCE")
    if spec.mode is GenerationMode.PRODUCT_SCENE and not any(
        item.role.value == "IDENTITY" for item in spec.references
    ):
        raise ImageGenerationPipelineError("PRODUCT_SCENE_IDENTITY_REFERENCE_REQUIRED")
    if spec.mode is GenerationMode.STYLE_REFERENCE and not any(
        item.role.value == "STYLE" for item in spec.references
    ):
        raise ImageGenerationPipelineError("STYLE_REFERENCE_ROLE_REQUIRED")

def _request(
    *,
    spec: ImageGenerationSpec,
    generation_id: UUID,
    variant_index: int,
    prompt,
    references,
    budget: Decimal,
) -> GatewayRequest:
    operation_id = _variant_operation_id(spec.operation_id, variant_index)
    return GatewayRequest(
        request_id=_request_id(operation_id),
        organization_id=spec.organization_id,
        project_id=spec.project_id,
        task_id=spec.task_id,
        root_operation_id=spec.operation_id,
        variant_operation_id=operation_id,
        generation_id=generation_id,
        variant_index=variant_index,
        mode=spec.mode,
        prompt=prompt,
        references=references,
        target_width=spec.target_width,
        target_height=spec.target_height,
        quality_profile=spec.quality_profile,
        budget_limit_usd=budget,
        constraints=spec.constraints,
        output_requirements=spec.output_requirements,
        seed=(spec.seed + variant_index - 1 if spec.seed is not None else None),
        agent_run_id=spec.agent_run_id,
    )

def _replace_candidate(job: GenerationJob, candidate: GenerationCandidate) -> GenerationJob:
    values = [item for item in job.candidates if item.candidate_id != candidate.candidate_id]
    values.append(candidate)
    values.sort(key=lambda item: item.variant_index)
    return replace(job, candidates=tuple(values))

def _safety(validation: ValidationBundle, result: GatewayResult) -> ValidationBundle:
    blocked = result.safety_metadata.get("blocked") is True or result.finish_reason in {
        "content_filter",
        "safety_block",
    }
    if not blocked:
        return validation
    finding = ValidationFinding(
        "model-gateway-safety",
        ValidationStatus.FAIL,
        ConstraintSeverity.HARD,
        "GENERATION_PROVIDER_SAFETY_BLOCK",
        evidence_refs=(
            f"provider:{result.provider}",
            f"provider_request:{result.provider_request_id or 'unknown'}",
        ),
    )
    return replace(validation, findings=validation.findings + (finding,))
