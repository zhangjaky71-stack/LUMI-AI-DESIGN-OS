from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from .model import CandidateStatus, GatewayStatus, GenerationJob, JobStatus
from .ports import PendingInvocation
from .pipeline_support import _replace_candidate, _request

async def execute(
    pipeline, *, organization_id: UUID, generation_id: UUID, now: str
) -> GenerationJob:
    job = pipeline._job(organization_id, generation_id)
    if job.status in {
        JobStatus.COMPLETED,
        JobStatus.PARTIAL,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }:
        return job
    spec = pipeline._spec(job)
    try:
        authorized = pipeline.references.authorize(spec, spec.references)
    except Exception as exc:
        return await pipeline._fail_all(
            job,
            now=now,
            code=f"GENERATION_REFERENCE_AUTHORIZATION:{type(exc).__name__}",
        )
    job = replace(job, status=JobStatus.RUNNING, updated_at=now)
    pipeline.repository.save(job)
    per_variant = spec.budget_limit_usd / Decimal(job.variant_decision.selected_count)
    for current in tuple(job.candidates):
        if current.status is not CandidateStatus.QUEUED:
            continue
        request = _request(
            spec=spec,
            generation_id=job.generation_id,
            variant_index=current.variant_index,
            prompt=job.prompt,
            references=authorized,
            budget=per_variant,
        )
        try:
            result = await pipeline.gateway.invoke(request)
        except Exception as exc:
            failed = replace(
                current,
                status=CandidateStatus.FAILED,
                error_code=f"GENERATION_GATEWAY_EXCEPTION:{type(exc).__name__}",
            )
            job = _replace_candidate(job, failed)
            pipeline.repository.save(job)
            continue
        await pipeline.events.emit(
            "generation.provider_submitted",
            organization_id=organization_id,
            generation_id=generation_id,
            payload={
                "candidate_id": str(current.candidate_id),
                "variant_index": current.variant_index,
                "provider": result.provider,
                "model": result.model,
                "provider_request_id": result.provider_request_id or "",
                "status": result.status.value,
            },
        )
        await pipeline._project_cost(job.generation_id, current, result)
        if result.status is GatewayStatus.PENDING:
            if not result.provider_request_id:
                candidate = replace(
                    current,
                    status=CandidateStatus.FAILED,
                    error_code="GENERATION_PENDING_PROVIDER_REQUEST_ID_MISSING",
                )
            else:
                candidate = replace(
                    current,
                    status=CandidateStatus.PROVIDER_PENDING,
                    provider=result.provider,
                    model=result.model,
                    provider_request_id=result.provider_request_id,
                    model_revision=result.model_revision,
                    registry_snapshot_id=result.registry_snapshot_id,
                    cost_usd=result.cost_usd,
                    cost_confidence=result.cost_confidence,
                    pricing_snapshot_id=result.pricing_snapshot_id,
                    routing_reason_codes=result.routing_reason_codes,
                )
                pipeline.repository.save_pending(
                    PendingInvocation(
                        organization_id,
                        generation_id,
                        current.candidate_id,
                        request,
                        result,
                        now,
                    )
                )
        elif result.status is GatewayStatus.COMPLETED:
            candidate = await pipeline._complete(
                spec=spec,
                authorized=authorized,
                request=request,
                current=current,
                result=result,
            )
        else:
            candidate = replace(
                current,
                status=CandidateStatus.FAILED,
                provider=result.provider,
                model=result.model,
                provider_request_id=result.provider_request_id,
                error_code=f"GENERATION_PROVIDER_{result.status.value}",
                cost_usd=result.cost_usd,
                cost_confidence=result.cost_confidence,
                pricing_snapshot_id=result.pricing_snapshot_id,
                routing_reason_codes=result.routing_reason_codes,
            )
        job = _replace_candidate(job, candidate)
        pipeline.repository.save(job)
    return await pipeline._finalize(job, now=now)


async def resume_pending(
    pipeline, *, organization_id: UUID, generation_id: UUID, now: str
) -> GenerationJob:
    job = pipeline._job(organization_id, generation_id)
    spec = pipeline._spec(job)
    try:
        authorized = pipeline.references.authorize(spec, spec.references)
        authorization_error = None
    except Exception as exc:
        authorized = ()
        authorization_error = exc
    for current in tuple(job.candidates):
        if current.status is not CandidateStatus.PROVIDER_PENDING:
            continue
        pending = pipeline.repository.get_pending(
            organization_id, generation_id, current.candidate_id
        )
        if pending is None:
            candidate = replace(
                current,
                status=CandidateStatus.FAILED,
                error_code="GENERATION_PENDING_STATE_MISSING",
            )
            job = _replace_candidate(job, candidate)
            continue
        try:
            result = await pipeline.gateway.poll(
                request=pending.request,
                pending_result=pending.result,
            )
        except Exception as exc:
            deferred = replace(
                current,
                error_code=f"GENERATION_POLL_DEFERRED:{type(exc).__name__}",
            )
            pipeline.repository.save_pending(
                replace(
                    pending,
                    last_polled_at=now,
                    poll_attempts=pending.poll_attempts + 1,
                )
            )
            job = _replace_candidate(job, deferred)
            pipeline.repository.save(job)
            continue
        await pipeline._project_cost(job.generation_id, current, result)
        if result.status is GatewayStatus.PENDING:
            pipeline.repository.save_pending(
                replace(
                    pending,
                    result=result,
                    last_polled_at=now,
                    poll_attempts=pending.poll_attempts + 1,
                )
            )
            job = _replace_candidate(job, replace(current, error_code=None))
            pipeline.repository.save(job)
            continue
        pipeline.repository.delete_pending(
            organization_id, generation_id, current.candidate_id
        )
        if authorization_error is not None:
            candidate = replace(
                current,
                status=CandidateStatus.REJECTED,
                provider=result.provider,
                model=result.model,
                provider_request_id=result.provider_request_id,
                error_code="GENERATION_REFERENCE_AUTHORIZATION_REVOKED",
            )
        elif result.status is GatewayStatus.COMPLETED:
            candidate = await pipeline._complete(
                spec=spec,
                authorized=authorized,
                request=pending.request,
                current=current,
                result=result,
            )
        else:
            candidate = replace(
                current,
                status=CandidateStatus.FAILED,
                provider=result.provider,
                model=result.model,
                provider_request_id=result.provider_request_id,
                error_code=f"GENERATION_PROVIDER_{result.status.value}",
            )
        job = _replace_candidate(job, candidate)
        pipeline.repository.save(job)
    return await pipeline._finalize(job, now=now)
