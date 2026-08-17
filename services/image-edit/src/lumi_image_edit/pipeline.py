from __future__ import annotations

from dataclasses import replace

from .mask import validate_mask
from .model import EditJob, GatewayEditRequest, ImageEditSpec
from .planner import plan_edit
from .ports import (
    ArtifactEditPort,
    CanvasUpdatePort,
    EditAuditPort,
    EditCostProjectionPort,
    EditRepositoryPort,
    EventSinkPort,
    ImageEditGatewayPort,
    OutputMaterializerPort,
    PostflightPort,
    ProtectedCompositorPort,
    SourceAuthorizationPort,
    StructuralEditPort,
)
from .pipeline_completion import handle
from .pipeline_lifecycle import (
    approve_mask as _approve_mask,
    cancel as _cancel,
    confirm_broad_change as _confirm_broad_change,
)
from .pipeline_support import (
    ImageEditPipelineError,
    assert_source_unchanged,
    edit_id,
)


class ImageEditPipeline:
    def __init__(
        self,
        *,
        repository: EditRepositoryPort,
        authorization: SourceAuthorizationPort,
        structural: StructuralEditPort,
        gateway: ImageEditGatewayPort,
        materializer: OutputMaterializerPort,
        postflight: PostflightPort,
        artifacts: ArtifactEditPort,
        canvas: CanvasUpdatePort,
        events: EventSinkPort,
        compositor: ProtectedCompositorPort | None = None,
        costs: EditCostProjectionPort | None = None,
        audit: EditAuditPort | None = None,
    ) -> None:
        self.repository = repository
        self.authorization = authorization
        self.structural = structural
        self.gateway = gateway
        self.materializer = materializer
        self.postflight = postflight
        self.artifacts = artifacts
        self.canvas = canvas
        self.events = events
        self.compositor = compositor
        self.costs = costs
        self.audit = audit

    async def submit(self, spec: ImageEditSpec) -> EditJob:
        prior = self.repository.get_by_operation(
            spec.organization_id,
            spec.operation_id,
        )
        if prior:
            if prior.semantic_hash != spec.semantic_hash:
                raise ImageEditPipelineError(
                    "IMAGE_EDIT_OPERATION_SEMANTIC_CONFLICT"
                )
            return prior

        source = self.authorization.authorize_current(spec)
        assert_source_unchanged(spec, source)
        plan = plan_edit(spec)
        current_edit_id = edit_id(spec)

        if spec.mask:
            try:
                validate_mask(spec.mask, source, spec.protected_regions)
            except PermissionError:
                job = EditJob(
                    current_edit_id,
                    spec.organization_id,
                    spec.operation_id,
                    spec.semantic_hash,
                    plan.route,
                    "AWAITING_MASK_APPROVAL",
                    spec.source.artifact_version_id,
                    plan.reason_codes,
                )
                self._save(spec, job)
                return job

        if plan.requires_user_confirmation and not spec.intent.broad_change_confirmed:
            job = EditJob(
                current_edit_id,
                spec.organization_id,
                spec.operation_id,
                spec.semantic_hash,
                plan.route,
                "AWAITING_CONFIRMATION",
                spec.source.artifact_version_id,
                plan.reason_codes,
            )
            self._save(spec, job)
            return job

        if plan.route == "STRUCTURAL_IR_EDIT":
            version = await self.structural.apply(
                spec,
                plan.structural_operations,
            )
            job = EditJob(
                current_edit_id,
                spec.organization_id,
                spec.operation_id,
                spec.semantic_hash,
                plan.route,
                "COMPLETED",
                spec.source.artifact_version_id,
                plan.reason_codes,
                result_design_document_version_id=version,
                validation_decision="PASS",
            )
            self._save(spec, job)
            await self.events.emit(
                "image_edit.completed",
                organization_id=spec.organization_id,
                edit_id=current_edit_id,
                payload={
                    "route": plan.route,
                    "provider_invoked": False,
                },
            )
            return job

        job = EditJob(
            current_edit_id,
            spec.organization_id,
            spec.operation_id,
            spec.semantic_hash,
            plan.route,
            "QUEUED",
            spec.source.artifact_version_id,
            plan.reason_codes,
        )
        self._save(spec, job)
        await self.events.emit(
            "image_edit.queued",
            organization_id=spec.organization_id,
            edit_id=current_edit_id,
            payload={"route": plan.route},
        )
        return job

    def _save(self, spec: ImageEditSpec, job: EditJob) -> None:
        bind = getattr(self.repository, "bind_spec", None)
        if bind:
            bind(job.edit_id, spec)
        else:
            self.repository.save_spec(spec)
        self.repository.save(job)

    async def execute(
        self,
        *,
        organization_id: str,
        edit_id_value: str,
    ) -> EditJob:
        job = self.repository.get(organization_id, edit_id_value)
        if not job:
            raise LookupError("IMAGE_EDIT_NOT_FOUND")
        if job.status not in {"QUEUED", "RUNNING"}:
            return job

        spec = self.repository.get_spec(organization_id, edit_id_value)
        source = self.authorization.authorize_current(spec)
        assert_source_unchanged(spec, source)
        plan = plan_edit(spec)
        request = GatewayEditRequest(
            spec.organization_id,
            spec.project_id,
            spec.task_id,
            spec.operation_id,
            job.edit_id,
            plan.route,
            source.durable_ref,
            spec.mask.durable_ref if spec.mask else None,
            spec.intent.instruction,
            plan.required_capabilities,
            spec.protected_regions,
            (),
            spec.budget_limit_usd,
            spec.seed,
        )
        running = replace(job, status="RUNNING")
        self.repository.save(running)
        try:
            result = await self.gateway.invoke(request)
        except Exception as exc:
            failed = replace(
                running,
                status="FAILED",
                error_code=(
                    "IMAGE_EDIT_PROVIDER_EXCEPTION:"
                    f"{type(exc).__name__}"
                ),
            )
            self.repository.save(failed)
            return failed
        return await handle(self, spec, source, request, running, result)

    async def resume_pending(
        self,
        *,
        organization_id: str,
        edit_id_value: str,
    ) -> EditJob:
        job = self.repository.get(organization_id, edit_id_value)
        if not job:
            raise LookupError("IMAGE_EDIT_NOT_FOUND")
        pending = self.repository.get_pending(edit_id_value)
        if job.status != "PROVIDER_PENDING" or not pending:
            return job
        request, old_result = pending
        spec = self.repository.get_spec(organization_id, edit_id_value)
        source = self.authorization.authorize_current(spec)
        assert_source_unchanged(spec, source)
        try:
            result = await self.gateway.poll(request, old_result)
        except Exception as exc:
            deferred = replace(
                job,
                error_code=(
                    "IMAGE_EDIT_POLL_DEFERRED:"
                    f"{type(exc).__name__}"
                ),
            )
            self.repository.save(deferred)
            return deferred
        return await handle(self, spec, source, request, job, result)

    async def approve_mask(
        self,
        *,
        organization_id: str,
        edit_id_value: str,
        approved_by: str,
    ) -> EditJob:
        return await _approve_mask(
            self,
            organization_id=organization_id,
            edit_id_value=edit_id_value,
            approved_by=approved_by,
        )

    async def confirm_broad_change(
        self,
        *,
        organization_id: str,
        edit_id_value: str,
        confirmed_by: str,
    ) -> EditJob:
        return await _confirm_broad_change(
            self,
            organization_id=organization_id,
            edit_id_value=edit_id_value,
            confirmed_by=confirmed_by,
        )

    async def cancel(
        self,
        *,
        organization_id: str,
        edit_id_value: str,
    ) -> EditJob:
        return await _cancel(
            self,
            organization_id=organization_id,
            edit_id_value=edit_id_value,
        )
