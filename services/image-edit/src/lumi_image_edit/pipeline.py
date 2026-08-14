from __future__ import annotations

import hashlib
from dataclasses import replace

from .hashing import constraint_snapshot_hash, protected_region_hash, validation_report_hash
from .mask import assert_no_hard_protected_overlap
from .model import (
    EditFinding,
    EditJob,
    EditPlan,
    EditProvenanceSnapshot,
    EditValidationReport,
    GatewayEditResult,
    ImageEditSpec,
    StructuralEditOperation,
)
from .planner import plan_edit
from .ports import (
    ArtifactEditPort,
    EditCostPort,
    EditedOutputPort,
    EditEventPort,
    EditModelGatewayPort,
    EditRepositoryPort,
    EditValidationPort,
    ProtectedCompositePort,
    StoredEditedImage,
    StructuralEditPort,
)
from .repository import ImageEditOperationConflict


def _edit_id(spec: ImageEditSpec) -> str:
    digest = hashlib.sha256(
        f"{spec.organization_id}:{spec.operation_id}:{spec.semantic_hash}".encode()
    ).hexdigest()
    return f"image-edit:{digest}"


def _safety(report: EditValidationReport, result: GatewayEditResult) -> EditValidationReport:
    blocked = result.safety_metadata.get("blocked") is True
    if not blocked:
        return report
    return replace(report, findings=report.findings + (EditFinding(
        validator="model-gateway-safety",
        status="FAIL",
        severity="HARD",
        reason_code="IMAGE_EDIT_PROVIDER_SAFETY_BLOCK",
    ),))


def _replace_asset_operation(spec: ImageEditSpec, candidate: StoredEditedImage) -> StructuralEditOperation:
    if spec.design_document_version is None or not spec.intent.selected_node_ids:
        raise ValueError("IMAGE_EDIT_CANVAS_REPLACE_CONTEXT_MISSING")
    return StructuralEditOperation(
        operation_id=f"{spec.operation_id}:replace-asset",
        type="REPLACE_ASSET",
        target_ids=spec.intent.selected_node_ids,
        expected_document_version=spec.design_document_version,
        payload={"asset_ref": candidate.durable_asset_ref},
        reason="IMAGE_EDIT_PIXEL_RESULT_REPLACE_ASSET",
    )


class ImageEditPipeline:
    def __init__(
        self,
        *,
        repository: EditRepositoryPort,
        structural: StructuralEditPort,
        gateway: EditModelGatewayPort,
        output: EditedOutputPort,
        validator: EditValidationPort,
        composite: ProtectedCompositePort,
        artifacts: ArtifactEditPort,
        costs: EditCostPort,
        events: EditEventPort,
    ) -> None:
        self.repository = repository
        self.structural = structural
        self.gateway = gateway
        self.output = output
        self.validator = validator
        self.composite = composite
        self.artifacts = artifacts
        self.costs = costs
        self.events = events

    async def start(self, spec: ImageEditSpec) -> EditJob:
        existing = self.repository.get_by_operation(spec.organization_id, spec.operation_id)
        if existing is not None:
            if existing.semantic_hash != spec.semantic_hash:
                raise ImageEditOperationConflict("IMAGE_EDIT_OPERATION_SEMANTIC_CONFLICT")
            return existing

        plan = plan_edit(spec)
        if plan.requires_provider and not spec.source.commercial_use_allowed:
            raise ValueError("IMAGE_EDIT_SOURCE_COMMERCIAL_RIGHTS_NOT_ALLOWED")
        edit_id = _edit_id(spec)
        job = EditJob(
            edit_id=edit_id,
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
            semantic_hash=spec.semantic_hash,
            route=plan.route,
            status="RUNNING",
            source_artifact_version_id=spec.source.artifact_version_id,
            plan_reason_codes=plan.reason_codes,
        )
        self.repository.save_spec(spec)
        self.repository.save(job)
        await self.events.emit("image_edit.started", organization_id=spec.organization_id, edit_id=edit_id, payload={"route": plan.route})

        if plan.route == "STRUCTURAL_IR_EDIT":
            result = await self.structural.apply(spec=spec, operations=plan.structural_operations)
            completed = replace(
                job,
                status="COMPLETED",
                result_artifact_version_id=result.artifact_version_id,
                result_design_document_version_id=result.design_document_version_id,
                validation_decision="PASS",
            )
            self.repository.save(completed)
            await self.events.emit("image_edit.completed", organization_id=spec.organization_id, edit_id=edit_id, payload={"route": plan.route, "model_invoked": False})
            return completed

        if plan.requires_mask:
            if spec.mask is None:
                rejected = replace(job, status="REJECTED", error_code="IMAGE_EDIT_MASK_REQUIRED")
                self.repository.save(rejected)
                return rejected
            assert_no_hard_protected_overlap(spec.mask.editable_rect, spec.protected_regions)

        try:
            result = await self.gateway.invoke(spec=spec, plan=plan, mask=spec.mask)
        except Exception as exc:
            failed = replace(job, status="FAILED", error_code=f"IMAGE_EDIT_GATEWAY_EXCEPTION:{type(exc).__name__}")
            self.repository.save(failed)
            return failed
        if result.status == "PENDING":
            pending = replace(job, status="PROVIDER_PENDING", provider=result.provider, model=result.model, provider_request_id=result.provider_request_id)
            self.repository.save_pending(spec.organization_id, edit_id, result)
            self.repository.save(pending)
            return pending
        return await self._complete(spec=spec, plan=plan, job=job, result=result)

    async def resume_pending(self, *, organization_id: str, operation_id: str) -> EditJob:
        job = self.repository.get_by_operation(organization_id, operation_id)
        if job is None:
            raise ValueError("IMAGE_EDIT_JOB_NOT_FOUND")
        if job.status != "PROVIDER_PENDING":
            return job
        spec = self.repository.get_spec(organization_id, operation_id)
        pending = self.repository.get_pending(organization_id, job.edit_id)
        if spec is None or pending is None:
            raise ValueError("IMAGE_EDIT_PENDING_STATE_MISSING")
        plan = plan_edit(spec)
        try:
            result = await self.gateway.poll(spec=spec, plan=plan, pending=pending, mask=spec.mask)
        except Exception:
            return job
        if result.status == "PENDING":
            self.repository.save_pending(organization_id, job.edit_id, result)
            return job
        self.repository.delete_pending(organization_id, job.edit_id)
        return await self._complete(spec=spec, plan=plan, job=job, result=result)

    async def _complete(self, *, spec: ImageEditSpec, plan: EditPlan, job: EditJob, result: GatewayEditResult) -> EditJob:
        await self.costs.record(
            edit_id=job.edit_id,
            operation_id=spec.operation_id,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            amount_usd=result.cost_usd,
            confidence=result.cost_confidence,
            pricing_snapshot_id=result.pricing_snapshot_id,
        )
        if result.status != "SUCCEEDED" or not result.output_ref:
            failed = replace(job, status="FAILED", provider=result.provider, model=result.model, provider_request_id=result.provider_request_id, error_code=f"IMAGE_EDIT_PROVIDER_{result.status}")
            self.repository.save(failed)
            return failed
        try:
            candidate = await self.output.materialize_and_store(
                spec=spec, output_ref=result.output_ref, declared_mime_type=result.output_mime_type
            )
            report = await self.validator.validate(spec=spec, plan=plan, candidate=candidate)
            report = _safety(report, result)
        except Exception as exc:
            failed = replace(job, status="FAILED", provider=result.provider, model=result.model, provider_request_id=result.provider_request_id, error_code=f"IMAGE_EDIT_POSTPROCESS_EXCEPTION:{type(exc).__name__}")
            self.repository.save(failed)
            return failed

        if report.decision == "REJECT" and spec.protected_regions and plan.route in {"PIXEL_LOCAL_EDIT", "REGENERATE_REGION", "HYBRID"}:
            candidate = await self.composite.composite_source_regions(source=spec.source, candidate=candidate, spec=spec)
            report = await self.validator.validate(spec=spec, plan=plan, candidate=candidate)
            report = _safety(report, result)

        provenance = EditProvenanceSnapshot(
            edit_id=job.edit_id,
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
            route=plan.route,
            source_artifact_version_id=spec.source.artifact_version_id,
            source_asset_ref=f"asset:{spec.source.asset_id}@{spec.source.asset_version}",
            source_checksum_sha256=spec.source.checksum_sha256,
            instruction_hash=hashlib.sha256(spec.intent.instruction.encode()).hexdigest(),
            mask_hash=spec.mask.checksum_sha256 if spec.mask else None,
            protected_region_hash=protected_region_hash(spec),
            constraint_snapshot_hash=constraint_snapshot_hash(spec),
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            routing_reason_codes=result.routing_reason_codes,
            pricing_snapshot_id=result.pricing_snapshot_id,
            cost_usd=result.cost_usd,
            cost_confidence=result.cost_confidence,
            seed=result.seed,
            code_git_sha=spec.code_git_sha,
            validation_decision=f"{report.decision}:{validation_report_hash(report)}",
            identity_validation_snapshot_id=report.identity_validation_snapshot_id,
        )
        artifact = await self.artifacts.create_version(
            spec=spec, candidate=candidate, provenance=provenance, validation=report
        )
        design_version: str | None = None
        if report.decision == "PASS" and spec.design_document_id is not None and spec.intent.selected_node_ids:
            structural_result = await self.structural.apply(
                spec=spec, operations=(_replace_asset_operation(spec, candidate),)
            )
            design_version = structural_result.design_document_version_id
        status = "COMPLETED" if report.decision == "PASS" else ("REPAIR_REQUIRED" if report.decision == "REPAIR" else "REJECTED")
        completed = replace(
            job,
            status=status,
            result_artifact_version_id=artifact.artifact_version_id,
            result_design_document_version_id=design_version,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            provenance_snapshot_id=provenance.snapshot_id,
            validation_decision=report.decision,
        )
        self.repository.save(completed)
        await self.events.emit(
            "image_edit.completed" if status == "COMPLETED" else "image_edit.rejected",
            organization_id=spec.organization_id,
            edit_id=job.edit_id,
            payload={"status": status, "artifact_version_id": artifact.artifact_version_id, "validation": report.decision},
        )
        return completed
