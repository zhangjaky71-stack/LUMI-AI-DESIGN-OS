from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from .image_validation import validate_provider_image
from .model import (
    CandidateStatus, GatewayRequest, GatewayResult, GenerationCandidate, GenerationJob,
    GenerationProvenance, ImageGenerationSpec, JobStatus, canonical_hash,
)
from .ports import CostProjection
from .pipeline_support import _replace_candidate, _safety

async def complete(
    pipeline,
    *,
    spec: ImageGenerationSpec,
    authorized,
    request: GatewayRequest,
    current: GenerationCandidate,
    result: GatewayResult,
) -> GenerationCandidate:
    if len(result.outputs) != 1:
        return replace(
            current,
            status=CandidateStatus.FAILED,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            error_code="GENERATION_PROVIDER_OUTPUT_COUNT_INVALID",
        )
    output = result.outputs[0]
    try:
        fetched = await pipeline.output_fetcher.fetch(output.ref, output.mime_type)
        image = validate_provider_image(fetched, spec)
        stored = await pipeline.storage.store(
            spec=spec,
            candidate_id=current.candidate_id,
            image=image,
        )
    except Exception as exc:
        return replace(
            current,
            status=CandidateStatus.FAILED,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            cost_usd=result.cost_usd,
            cost_confidence=result.cost_confidence,
            pricing_snapshot_id=result.pricing_snapshot_id,
            error_code=f"GENERATION_OUTPUT_INVALID:{type(exc).__name__}",
        )
    try:
        validation = await pipeline.validator.validate(
            spec=spec,
            candidate_id=current.candidate_id,
            image=image,
            stored=stored,
            references=authorized,
        )
        validation = _safety(validation, result)
        provenance = GenerationProvenance(
            generation_id=request.generation_id,
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            task_id=spec.task_id,
            operation_id=spec.operation_id,
            variant_operation_id=request.variant_operation_id,
            variant_index=request.variant_index,
            provider=result.provider,
            model=result.model,
            model_revision=result.model_revision,
            registry_snapshot_id=result.registry_snapshot_id,
            provider_request_id=result.provider_request_id,
            prompt_hash=request.prompt.prompt_hash,
            prompt_template_version=request.prompt.template_version,
            prompt_compilation_ref=spec.prompt_compilation_ref,
            reference_asset_ids=tuple(item.asset_id for item in authorized),
            reference_asset_versions=tuple(item.asset_version for item in authorized),
            seed=result.seed,
            width=stored.width,
            height=stored.height,
            quality_profile=spec.quality_profile,
            routing_reason_codes=result.routing_reason_codes,
            pricing_snapshot_id=result.pricing_snapshot_id,
            cost_usd=result.cost_usd,
            cost_confidence=result.cost_confidence,
            agent_run_id=spec.agent_run_id,
            agent_version=spec.agent_version,
            recipe_version=spec.recipe_version,
            skill_versions=spec.skill_versions,
            code_git_sha=spec.code_git_sha,
            constraint_snapshot_hash=canonical_hash(
                sorted(item.snapshot_hash for item in spec.constraints)
            ),
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
            brand_validation_snapshot_id=validation.brand_validation_snapshot_id,
            safety_metadata=result.safety_metadata,
            user_use_declaration=spec.user_use_declaration,
        )
        provisional = replace(
            current,
            status=CandidateStatus.VALIDATING,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            model_revision=result.model_revision,
            registry_snapshot_id=result.registry_snapshot_id,
            stored_image=stored,
            validation=validation,
            provenance_snapshot_id=provenance.snapshot_id,
            cost_usd=result.cost_usd,
            cost_confidence=result.cost_confidence,
            pricing_snapshot_id=result.pricing_snapshot_id,
            routing_reason_codes=result.routing_reason_codes,
        )
        artifact = await pipeline.artifacts.create_candidate(
            spec=spec,
            candidate=provisional,
            stored=stored,
            provenance=provenance,
            validation=validation,
        )
    except Exception as exc:
        return replace(
            current,
            status=CandidateStatus.FAILED,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            stored_image=stored,
            error_code=f"GENERATION_POSTFLIGHT_EXCEPTION:{type(exc).__name__}",
        )
    status = CandidateStatus.REJECTED if validation.hard_failed else CandidateStatus.READY
    if artifact.status not in {"DRAFT", "READY"}:
        status = CandidateStatus.REJECTED
    if status is CandidateStatus.READY and artifact.status != "READY":
        status = CandidateStatus.REJECTED
    return replace(
        provisional,
        status=status,
        artifact_id=artifact.artifact_id,
        artifact_version_id=artifact.artifact_version_id,
    )


async def project_cost(
    pipeline, generation_id: UUID, candidate: GenerationCandidate, result: GatewayResult
) -> None:
    await pipeline.costs.record(
        CostProjection(
            generation_id=generation_id,
            candidate_id=candidate.candidate_id,
            operation_id=candidate.variant_operation_id,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            amount_usd=result.cost_usd,
            confidence=result.cost_confidence,
            pricing_snapshot_id=result.pricing_snapshot_id,
        )
    )


async def finalize(pipeline, job: GenerationJob, *, now: str) -> GenerationJob:
    states = {item.status for item in job.candidates}
    if CandidateStatus.PROVIDER_PENDING in states:
        status = JobStatus.PROVIDER_PENDING
        completed_at = None
    elif all(item.status is CandidateStatus.READY for item in job.candidates):
        status = JobStatus.COMPLETED
        completed_at = now
    elif any(item.status is CandidateStatus.READY for item in job.candidates):
        status = JobStatus.PARTIAL
        completed_at = now
    elif all(
        item.status in {CandidateStatus.FAILED, CandidateStatus.REJECTED}
        for item in job.candidates
    ):
        status = JobStatus.FAILED
        completed_at = now
    else:
        status = JobStatus.RUNNING
        completed_at = None
    job = replace(job, status=status, updated_at=now, completed_at=completed_at)
    pipeline.repository.save(job)
    if completed_at:
        event = (
            "generation.completed"
            if status in {JobStatus.COMPLETED, JobStatus.PARTIAL}
            else "generation.failed"
        )
        await pipeline.events.emit(
            event,
            organization_id=job.organization_id,
            generation_id=job.generation_id,
            payload={
                "status": status.value,
                "ready": sum(item.status is CandidateStatus.READY for item in job.candidates),
                "rejected": sum(
                    item.status is CandidateStatus.REJECTED for item in job.candidates
                ),
                "failed": sum(item.status is CandidateStatus.FAILED for item in job.candidates),
            },
        )
    return job


async def fail_all(pipeline, job: GenerationJob, *, now: str, code: str) -> GenerationJob:
    for current in tuple(job.candidates):
        if current.status in {CandidateStatus.QUEUED, CandidateStatus.PROVIDER_PENDING}:
            job = _replace_candidate(
                job,
                replace(current, status=CandidateStatus.REJECTED, error_code=code),
            )
    job = replace(
        job,
        status=JobStatus.FAILED,
        updated_at=now,
        completed_at=now,
        error_code=code,
    )
    pipeline.repository.save(job)
    await pipeline.events.emit(
        "generation.failed",
        organization_id=job.organization_id,
        generation_id=job.generation_id,
        payload={"reason": code},
    )
    return job
