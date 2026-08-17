from __future__ import annotations

from dataclasses import replace

from .model import (
    EditJob,
    EditProvenance,
    GatewayEditRequest,
    GatewayEditResult,
    ImageEditSpec,
    SourceImageRef,
)
from .pipeline_support import (
    _with_provider_safety,
    constraint_hash,
    instruction_hash,
    protected_hash,
)


async def handle(
    pipeline,
    spec: ImageEditSpec,
    source: SourceImageRef,
    request: GatewayEditRequest,
    job: EditJob,
    result: GatewayEditResult,
) -> EditJob:
    if pipeline.costs is not None:
        await pipeline.costs.record(
            edit_id=job.edit_id,
            operation_id=spec.operation_id,
            result=result,
        )

    if result.status == "PENDING":
        pipeline.repository.save_pending(job.edit_id, request, result)
        pending = replace(
            job,
            status="PROVIDER_PENDING",
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            error_code=None,
        )
        pipeline.repository.save(pending)
        return pending

    pipeline.repository.delete_pending(job.edit_id)
    if result.status in {"FAILED", "CANCELLED"}:
        status = "CANCELLED" if result.status == "CANCELLED" else "FAILED"
        done = replace(
            job,
            status=status,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
        )
        pipeline.repository.save(done)
        return done

    image = await pipeline.materializer.materialize(
        spec=spec,
        edit_id=job.edit_id,
        result=result,
    )
    report = await pipeline.postflight.validate(
        spec=spec,
        image=image,
        source=source,
    )
    report = _with_provider_safety(report, result)

    if (
        report.decision == "REJECT"
        and pipeline.compositor
        and spec.protected_regions
    ):
        image = await pipeline.compositor.composite(
            spec=spec,
            generated=image,
            source=source,
        )
        report = await pipeline.postflight.validate(
            spec=spec,
            image=image,
            source=source,
        )
        report = _with_provider_safety(report, result)

    provenance = EditProvenance(
        edit_id=job.edit_id,
        operation_id=spec.operation_id,
        route=job.route,
        source_artifact_version_id=spec.source.artifact_version_id,
        source_checksum_sha256=spec.source.checksum_sha256,
        instruction_hash=instruction_hash(spec),
        mask_hash=spec.mask.checksum_sha256 if spec.mask else None,
        protected_region_hash=protected_hash(spec),
        constraint_snapshot_hash=constraint_hash(spec),
        provider=result.provider,
        model=result.model,
        model_revision=result.model_revision,
        registry_snapshot_id=result.registry_snapshot_id,
        provider_request_id=result.provider_request_id,
        routing_reason_codes=result.routing_reason_codes,
        pricing_snapshot_id=result.pricing_snapshot_id,
        cost_usd=result.cost_usd,
        cost_confidence=result.cost_confidence,
        seed=result.seed,
        agent_run_id=spec.agent_run_id,
        agent_version=spec.agent_version,
        recipe_version=spec.recipe_version,
        skill_versions=spec.skill_versions,
        code_git_sha=spec.code_git_sha,
        validation_decision=report.decision,
        identity_validation_snapshot_id=(
            report.identity_validation_snapshot_id
        ),
        safety_metadata=result.safety_metadata,
        finish_reason=result.finish_reason,
    )
    if pipeline.audit is not None:
        await pipeline.audit.record(
            provenance=provenance,
            validation=report,
        )

    artifact = await pipeline.artifacts.append_candidate(
        spec=spec,
        image=image,
        provenance=provenance,
        validation=report,
    )
    design_version = None
    if (
        report.decision == "PASS"
        and spec.design_document_id
        and spec.intent.selected_node_ids
    ):
        design_version = await pipeline.canvas.replace_asset(
            spec=spec,
            asset_id=artifact.asset_id,
        )
    status = {
        "PASS": "COMPLETED",
        "REPAIR": "REPAIR_REQUIRED",
        "REJECT": "REJECTED",
    }[report.decision]
    done = replace(
        job,
        status=status,
        result_artifact_version_id=artifact.artifact_version_id,
        result_design_document_version_id=design_version,
        result_asset_id=artifact.asset_id,
        provider=result.provider,
        model=result.model,
        provider_request_id=result.provider_request_id,
        provenance_snapshot_id=provenance.snapshot_id,
        validation_decision=report.decision,
        error_code=None,
    )
    pipeline.repository.save(done)
    await pipeline.events.emit(
        "image_edit.completed",
        organization_id=spec.organization_id,
        edit_id=job.edit_id,
        payload={
            "decision": report.decision,
            "artifact_version_id": artifact.artifact_version_id,
        },
    )
    return done
