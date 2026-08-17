from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from .model import (
    CandidateStatus,
    GenerationCandidate,
    GenerationJob,
    ImageGenerationSpec,
    JobStatus,
)
from .ports import (
    ArtifactCandidatePort, CostProjectionPort, DurableImageStorePort, GenerationEventSinkPort,
    GenerationRepositoryPort, GenerationValidationPort, GenerationWorkPublisherPort,
    ImageModelGatewayPort, ProviderOutputFetcherPort, ReferenceAuthorizationPort,
)
from .prompt import compile_prompt
from .repository import OperationSemanticConflict
from .variants import choose_variants
from .pipeline_support import (
    ImageGenerationPipelineError, _candidate_id, _generation_id, _replace_candidate,
    _request, _validate_reference_roles, _variant_operation_id,
)
from . import pipeline_completion as _completion
from . import pipeline_execution as _execution

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
        costs: CostProjectionPort,
        events: GenerationEventSinkPort,
        work: GenerationWorkPublisherPort | None = None,
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
        self.work = work

    async def submit(self, spec: ImageGenerationSpec, *, now: str) -> GenerationJob:
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
            generation_id=generation_id,
            variant_index=1,
            prompt=prompt,
            references=authorized,
            budget=spec.budget_limit_usd,
        )
        estimate = await self.gateway.estimate(representative)
        decision = choose_variants(spec, estimated_cost_per_variant_usd=estimate.amount_usd)
        candidates = tuple(
            GenerationCandidate(
                candidate_id=_candidate_id(generation_id, index),
                generation_id=generation_id,
                variant_index=index,
                variant_operation_id=_variant_operation_id(spec.operation_id, index),
                status=CandidateStatus.QUEUED,
            )
            for index in range(1, decision.selected_count + 1)
        )
        job = GenerationJob(
            generation_id=generation_id,
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            task_id=spec.task_id,
            operation_id=spec.operation_id,
            semantic_hash=spec.semantic_hash,
            status=JobStatus.QUEUED,
            prompt_hash=prompt.prompt_hash,
            prompt=prompt,
            authorized_references=authorized,
            variant_decision=decision,
            candidates=candidates,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_spec(spec)
        self.repository.save(job)
        await self.events.emit(
            "generation.started",
            organization_id=spec.organization_id,
            generation_id=generation_id,
            payload={
                "operation_id": str(spec.operation_id),
                "mode": spec.mode.value,
                "prompt_hash": prompt.prompt_hash,
                "requested_variants": decision.requested_count,
                "selected_variants": decision.selected_count,
                "variant_decision_reasons": list(decision.reason_codes),
            },
        )
        if self.work is not None:
            self.work.publish(spec.organization_id, generation_id)
        return job

    async def execute(
        self, *, organization_id: UUID, generation_id: UUID, now: str
    ) -> GenerationJob:
        return await _execution.execute(
            self, organization_id=organization_id, generation_id=generation_id, now=now
        )

    async def resume_pending(
        self, *, organization_id: UUID, generation_id: UUID, now: str
    ) -> GenerationJob:
        return await _execution.resume_pending(
            self, organization_id=organization_id, generation_id=generation_id, now=now
        )

    async def cancel(
        self, *, organization_id: UUID, generation_id: UUID, now: str
    ) -> GenerationJob:
        job = self._job(organization_id, generation_id)
        if job.status in {
            JobStatus.COMPLETED,
            JobStatus.PARTIAL,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            return job
        for current in tuple(job.candidates):
            if current.status is CandidateStatus.PROVIDER_PENDING:
                pending = self.repository.get_pending(
                    organization_id, generation_id, current.candidate_id
                )
                if pending is not None:
                    try:
                        await self.gateway.cancel(
                            request=pending.request,
                            pending_result=pending.result,
                        )
                    finally:
                        self.repository.delete_pending(
                            organization_id, generation_id, current.candidate_id
                        )
            if current.status in {CandidateStatus.QUEUED, CandidateStatus.PROVIDER_PENDING}:
                job = _replace_candidate(
                    job, replace(current, status=CandidateStatus.CANCELLED)
                )
        job = replace(job, status=JobStatus.CANCELLED, updated_at=now, completed_at=now)
        self.repository.save(job)
        await self.events.emit(
            "generation.failed",
            organization_id=organization_id,
            generation_id=generation_id,
            payload={"reason": "cancelled"},
        )
        return job

    async def _complete(self, **kwargs) -> GenerationCandidate:
        return await _completion.complete(self, **kwargs)

    async def _project_cost(self, generation_id, candidate, result) -> None:
        await _completion.project_cost(self, generation_id, candidate, result)

    async def _finalize(self, job: GenerationJob, *, now: str) -> GenerationJob:
        return await _completion.finalize(self, job, now=now)

    async def _fail_all(self, job: GenerationJob, *, now: str, code: str) -> GenerationJob:
        return await _completion.fail_all(self, job, now=now, code=code)

    def _job(self, organization_id: UUID, generation_id: UUID) -> GenerationJob:
        value = self.repository.get(organization_id, generation_id)
        if value is None:
            raise ImageGenerationPipelineError("GENERATION_JOB_NOT_FOUND")
        return value

    def _spec(self, job: GenerationJob) -> ImageGenerationSpec:
        value = self.repository.get_spec(job.organization_id, job.operation_id)
        if value is None:
            raise ImageGenerationPipelineError("GENERATION_SPEC_SNAPSHOT_MISSING")
        return value
