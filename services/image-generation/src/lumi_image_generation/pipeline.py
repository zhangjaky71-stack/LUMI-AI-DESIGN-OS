from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid5

from .hashing import constraint_snapshot_hash
from .image_validation import validate_provider_image
from .model import (
    AuthorizedReference,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GenerationCandidate,
    GenerationJob,
    GenerationProvenanceSnapshot,
    ImageGenerationSpec,
    PromptBlocks,
    ValidationBundle,
    ValidationFinding,
    canonical_hash,
)
from .ports import (
    ArtifactCandidatePort,
    CostReconciliationPort,
    DurableImageStorePort,
    GenerationEventSinkPort,
    GenerationRepositoryPort,
    GenerationValidationPort,
    ImageModelGatewayPort,
    PendingInvocationRecord,
    ProviderOutputFetcherPort,
    ReferenceAuthorizationPort,
)
from .prompt import compile_prompt
from .repository import OperationSemanticConflict
from .variants import choose_variants

_REFERENCE_REQUIRED_MODES = {"REFERENCE_TO_IMAGE", "PRODUCT_SCENE", "STYLE_REFERENCE"}


class ImageGenerationPipelineError(ValueError):
    pass


def _generation_id(spec: ImageGenerationSpec) -> str:
    digest = canonical_hash(
        {
            "organization_id": spec.organization_id,
            "operation_id": spec.operation_id,
            "semantic_hash": spec.semantic_hash,
        }
    )
    return f"image-generation:{digest}"


def _candidate_id(generation_id: str, variant_index: int) -> str:
    return f"image-candidate:{canonical_hash([generation_id, variant_index])}"


def _variant_operation_id(root_operation_id: str, variant_index: int) -> str:
    return str(uuid5(UUID(root_operation_id), f"image-generation-variant:{variant_index}"))


def _validate_reference_roles(spec: ImageGenerationSpec) -> None:
    if spec.mode in _REFERENCE_REQUIRED_MODES and not spec.references:
        raise ImageGenerationPipelineError("GENERATION_MODE_REQUIRES_REFERENCE")
    if spec.mode == "PRODUCT_SCENE" and not any(item.role == "IDENTITY" for item in spec.references):
        raise ImageGenerationPipelineError("PRODUCT_SCENE_IDENTITY_REFERENCE_REQUIRED")
    if spec.mode == "STYLE_REFERENCE" and not any(item.role == "STYLE" for item in spec.references):
        raise ImageGenerationPipelineError("STYLE_REFERENCE_ROLE_REQUIRED")


def _request(
    *,
    spec: ImageGenerationSpec,
    prompt: PromptBlocks,
    references: tuple[AuthorizedReference, ...],
    generation_id: str,
    variant_index: int,
    budget_limit_usd: Decimal,
) -> GatewayGenerationRequest:
    return GatewayGenerationRequest(
        organization_id=spec.organization_id,
        project_id=spec.project_id,
        task_id=spec.task_id,
        root_operation_id=spec.operation_id,
        variant_operation_id=_variant_operation_id(spec.operation_id, variant_index),
        generation_id=generation_id,
        variant_index=variant_index,
        mode=spec.mode,
        prompt=prompt,
        references=references,
        target_width=spec.target_width,
        target_height=spec.target_height,
        quality_profile=spec.quality_profile,
        budget_limit_usd=budget_limit_usd,
        constraints=spec.constraints,
        output_requirements=spec.output_requirements,
        seed=(spec.seed + variant_index - 1 if spec.seed is not None else None),
        agent_run_id=spec.agent_run_id,
    )


def _replace_candidate(job: GenerationJob, candidate: GenerationCandidate) -> GenerationJob:
    candidates = [item for item in job.candidates if item.candidate_id != candidate.candidate_id]
    candidates.append(candidate)
    candidates.sort(key=lambda item: item.variant_index)
    return replace(job, candidates=tuple(candidates))


def _safety_bundle(
    validation: ValidationBundle,
    result: GatewayGenerationResult,
) -> ValidationBundle:
    blocked = result.safety_metadata.get("blocked") is True or result.finish_reason in {
        "content_filter",
        "safety_block",
    }
    if not blocked:
        return validation
    finding = ValidationFinding(
        validator="model-gateway-safety",
        status="FAIL",
        severity="HARD",
        reason_code="GENERATION_PROVIDER_SAFETY_BLOCK",
        evidence_refs=(
            f"provider:{result.provider}",
            f"provider_request:{result.provider_request_id or 'unknown'}",
        ),
    )
    return replace(validation, findings=validation.findings + (finding,))


class ImageGenerationPipeline:
    def __init__(
        self,
        *,
        repository: GenerationRepositoryPort,
        references: ReferenceAuthorizationPort,
        gateway: ImageModelGatewayPort,
        output_fetcher: ProviderOutputFetcherPort,
        storage: DurableImageStorePort,
        validator: GenerationValidationPort,
        artifacts: ArtifactCandidatePort,
        costs: CostReconciliationPort,
        events: GenerationEventSinkPort,
    ) -> None:
        self.repository = repository
        self.references = references
        self.gateway = gateway
        self.output_fetcher = output_fetcher
        self.storage = storage
        self.validator = validator
        self.artifacts = artifacts
        self.costs = costs
        self.events = events

    async def start(self, spec: ImageGenerationSpec, *, created_at: str) -> GenerationJob:
        existing = self.repository.get_by_operation(spec.organization_id, spec.operation_id)
        if existing is not None:
            if existing.semantic_hash != spec.semantic_hash:
                raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")
            return existing

        _validate_reference_roles(spec)
        authorized = self.references.authorize(spec, spec.references)
        prompt = compile_prompt(spec)
        generation_id = _generation_id(spec)
        representative = _request(
            spec=spec,
            prompt=prompt,
            references=authorized,
            generation_id=generation_id,
            variant_index=1,
            budget_limit_usd=spec.budget_limit_usd,
        )
        estimate = await self.gateway.estimate(representative)
        decision = choose_variants(spec, estimated_cost_per_variant_usd=estimate.amount_usd)

        job = GenerationJob(
            generation_id=generation_id,
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            task_id=spec.task_id,
            operation_id=spec.operation_id,
            semantic_hash=spec.semantic_hash,
            status="RUNNING",
            prompt_hash=prompt.prompt_hash,
            variant_decision=decision,
            candidates=(),
            created_at=created_at,
        )
        self.repository.save_spec(spec)
        self.repository.save(job)
        await self.events.emit(
            "generation.started",
            organization_id=spec.organization_id,
            generation_id=generation_id,
            payload={
                "operation_id": spec.operation_id,
                "mode": spec.mode,
                "prompt_hash": prompt.prompt_hash,
                "requested_variants": decision.requested_count,
                "selected_variants": decision.selected_count,
                "variant_decision_reasons": decision.reason_codes,
            },
        )

        per_variant_budget = spec.budget_limit_usd / Decimal(decision.selected_count)
        for variant_index in range(1, decision.selected_count + 1):
            candidate_id = _candidate_id(generation_id, variant_index)
            request = _request(
                spec=spec,
                prompt=prompt,
                references=authorized,
                generation_id=generation_id,
                variant_index=variant_index,
                budget_limit_usd=per_variant_budget,
            )
            try:
                result = await self.gateway.invoke(request)
            except Exception as exc:
                candidate = GenerationCandidate(
                    candidate_id=candidate_id,
                    generation_id=generation_id,
                    variant_index=variant_index,
                    status="FAILED",
                    error_code=f"GENERATION_GATEWAY_EXCEPTION:{type(exc).__name__}",
                )
                job = _replace_candidate(job, candidate)
                self.repository.save(job)
                continue

            await self.events.emit(
                "generation.provider_submitted",
                organization_id=spec.organization_id,
                generation_id=generation_id,
                payload={
                    "candidate_id": candidate_id,
                    "variant_index": variant_index,
                    "provider": result.provider,
                    "model": result.model,
                    "provider_request_id": result.provider_request_id or "",
                    "status": result.status,
                },
            )

            if result.status == "PENDING":
                candidate = GenerationCandidate(
                    candidate_id=candidate_id,
                    generation_id=generation_id,
                    variant_index=variant_index,
                    status="PROVIDER_PENDING",
                    provider=result.provider,
                    model=result.model,
                    provider_request_id=result.provider_request_id,
                )
                self.repository.save_pending(
                    PendingInvocationRecord(
                        organization_id=spec.organization_id,
                        generation_id=generation_id,
                        candidate_id=candidate_id,
                        variant_index=variant_index,
                        request=request,
                        result=result,
                    )
                )
            elif result.status == "SUCCEEDED":
                candidate = await self._complete_candidate(
                    spec=spec,
                    authorized=authorized,
                    request=request,
                    candidate_id=candidate_id,
                    result=result,
                )
            else:
                await self._record_cost(
                    generation_id=generation_id,
                    candidate_id=candidate_id,
                    request=request,
                    result=result,
                )
                candidate = GenerationCandidate(
                    candidate_id=candidate_id,
                    generation_id=generation_id,
                    variant_index=variant_index,
                    status="FAILED",
                    provider=result.provider,
                    model=result.model,
                    provider_request_id=result.provider_request_id,
                    error_code=f"GENERATION_PROVIDER_{result.status}",
                )
            job = _replace_candidate(job, candidate)
            self.repository.save(job)

        job = await self._finalize(job, completed_at=created_at)
        return job

    async def resume_pending(
        self,
        *,
        organization_id: str,
        generation_id: str,
        completed_at: str,
    ) -> GenerationJob:
        job = self.repository.get(organization_id, generation_id)
        if job is None:
            raise ImageGenerationPipelineError("GENERATION_JOB_NOT_FOUND")
        spec = self.repository.get_spec(organization_id, job.operation_id)
        if spec is None:
            raise ImageGenerationPipelineError("GENERATION_SPEC_SNAPSHOT_MISSING")

        authorization_error: Exception | None = None
        try:
            authorized = self.references.authorize(spec, spec.references)
        except Exception as exc:
            authorization_error = exc
            authorized = ()

        for candidate in tuple(job.candidates):
            if candidate.status != "PROVIDER_PENDING":
                continue
            pending = self.repository.get_pending(
                organization_id,
                generation_id,
                candidate.candidate_id,
            )
            if pending is None:
                failed = replace(
                    candidate,
                    status="FAILED",
                    error_code="GENERATION_PENDING_STATE_MISSING",
                )
                job = _replace_candidate(job, failed)
                self.repository.save(job)
                continue

            try:
                result = await self.gateway.poll(
                    request=pending.request,
                    pending_result=pending.result,
                )
            except Exception as exc:
                failed = replace(
                    candidate,
                    status="FAILED",
                    error_code=f"GENERATION_POLL_EXCEPTION:{type(exc).__name__}",
                )
                job = _replace_candidate(job, failed)
                self.repository.save(job)
                continue

            if result.status == "PENDING":
                self.repository.save_pending(replace(pending, result=result))
                continue

            self.repository.delete_pending(
                organization_id,
                generation_id,
                candidate.candidate_id,
            )
            if result.status == "SUCCEEDED" and authorization_error is None:
                completed = await self._complete_candidate(
                    spec=spec,
                    authorized=authorized,
                    request=pending.request,
                    candidate_id=candidate.candidate_id,
                    result=result,
                )
            else:
                await self._record_cost(
                    generation_id=generation_id,
                    candidate_id=candidate.candidate_id,
                    request=pending.request,
                    result=result,
                )
                error_code = (
                    "GENERATION_REFERENCE_AUTHORIZATION_REVOKED"
                    if authorization_error is not None
                    else f"GENERATION_PROVIDER_{result.status}"
                )
                completed = replace(
                    candidate,
                    status="REJECTED" if authorization_error is not None else "FAILED",
                    provider=result.provider,
                    model=result.model,
                    provider_request_id=result.provider_request_id,
                    error_code=error_code,
                )
            job = _replace_candidate(job, completed)
            self.repository.save(job)

        return await self._finalize(job, completed_at=completed_at)

    async def _complete_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        authorized: tuple[AuthorizedReference, ...],
        request: GatewayGenerationRequest,
        candidate_id: str,
        result: GatewayGenerationResult,
    ) -> GenerationCandidate:
        await self._record_cost(
            generation_id=request.generation_id,
            candidate_id=candidate_id,
            request=request,
            result=result,
        )
        if len(result.outputs) != 1:
            return GenerationCandidate(
                candidate_id=candidate_id,
                generation_id=request.generation_id,
                variant_index=request.variant_index,
                status="FAILED",
                provider=result.provider,
                model=result.model,
                provider_request_id=result.provider_request_id,
                error_code="GENERATION_PROVIDER_OUTPUT_COUNT_INVALID",
            )

        output = result.outputs[0]
        try:
            fetched = await self.output_fetcher.fetch(output.ref, output.mime_type)
            image = validate_provider_image(fetched, spec)
            stored = await self.storage.store(
                spec=spec,
                candidate_id=candidate_id,
                image=image,
            )
        except Exception as exc:
            return GenerationCandidate(
                candidate_id=candidate_id,
                generation_id=request.generation_id,
                variant_index=request.variant_index,
                status="FAILED",
                provider=result.provider,
                model=result.model,
                provider_request_id=result.provider_request_id,
                provider_output_ref=output.ref,
                error_code=f"GENERATION_OUTPUT_INVALID:{type(exc).__name__}",
            )

        validation = await self.validator.validate(
            spec=spec,
            candidate_id=candidate_id,
            image=image,
            stored=stored,
            references=authorized,
        )
        validation = _safety_bundle(validation, result)
        provenance = GenerationProvenanceSnapshot(
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
            provider_request_id=result.provider_request_id,
            prompt_hash=request.prompt.prompt_hash,
            prompt_template_version=request.prompt.template_version,
            prompt_compilation_ref=spec.prompt_compilation_ref,
            reference_asset_refs=tuple(
                f"asset:{reference.asset_id}@{reference.asset_version}" for reference in authorized
            ),
            seed=result.seed,
            width=stored.width,
            height=stored.height,
            quality_profile=spec.quality_profile,
            routing_reason_codes=result.routing_reason_codes,
            pricing_snapshot_id=result.pricing_snapshot_id,
            cost_usd=result.cost_usd,
            cost_confidence=result.cost_confidence,
            agent_run_id=spec.agent_run_id,
            recipe_version=spec.recipe_version,
            skill_versions=spec.skill_versions,
            code_git_sha=spec.code_git_sha,
            constraint_snapshot_hash=constraint_snapshot_hash(spec),
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
            safety_metadata=result.safety_metadata,
        )
        provisional = GenerationCandidate(
            candidate_id=candidate_id,
            generation_id=request.generation_id,
            variant_index=request.variant_index,
            status="VALIDATING",
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            provider_output_ref=output.ref,
            stored_image=stored,
            validation=validation,
            provenance_snapshot_id=provenance.snapshot_id,
        )
        artifact = await self.artifacts.create_candidate(
            spec=spec,
            candidate=provisional,
            stored=stored,
            provenance=provenance,
            validation=validation,
        )
        status = "REJECTED" if validation.hard_failed or artifact.status == "REJECTED" else "READY"
        completed = replace(
            provisional,
            status=status,
            artifact_id=artifact.artifact_id,
            artifact_version_id=artifact.artifact_version_id,
        )
        await self.events.emit(
            "artifact.version.created",
            organization_id=spec.organization_id,
            generation_id=request.generation_id,
            payload={
                "candidate_id": candidate_id,
                "artifact_id": artifact.artifact_id,
                "artifact_version_id": artifact.artifact_version_id,
                "status": status,
                "provenance_snapshot_id": provenance.snapshot_id,
            },
        )
        return completed

    async def _record_cost(
        self,
        *,
        generation_id: str,
        candidate_id: str,
        request: GatewayGenerationRequest,
        result: GatewayGenerationResult,
    ) -> None:
        await self.costs.record_generation_result(
            generation_id=generation_id,
            candidate_id=candidate_id,
            operation_id=request.variant_operation_id,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            amount_usd=result.cost_usd,
            confidence=result.cost_confidence,
            pricing_snapshot_id=result.pricing_snapshot_id,
        )

    async def _finalize(self, job: GenerationJob, *, completed_at: str) -> GenerationJob:
        if any(candidate.status == "PROVIDER_PENDING" for candidate in job.candidates):
            updated = replace(job, status="PROVIDER_PENDING")
            self.repository.save(updated)
            return updated

        ready = sum(candidate.status == "READY" for candidate in job.candidates)
        if ready == len(job.candidates) and ready > 0:
            status = "COMPLETED"
            error_code = None
        elif ready > 0:
            status = "PARTIAL"
            error_code = "GENERATION_PARTIAL_CANDIDATES"
        else:
            status = "FAILED"
            error_code = "GENERATION_NO_READY_CANDIDATES"
        updated = replace(
            job,
            status=status,
            completed_at=completed_at,
            error_code=error_code,
        )
        self.repository.save(updated)
        event_type = "generation.failed" if status == "FAILED" else "generation.completed"
        await self.events.emit(
            event_type,
            organization_id=job.organization_id,
            generation_id=job.generation_id,
            payload={
                "status": status,
                "ready_candidates": ready,
                "candidate_count": len(job.candidates),
                "error_code": error_code or "",
            },
        )
        return updated
