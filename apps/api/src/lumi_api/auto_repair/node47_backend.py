from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from lumi_api.artifact_engine.ports import ArtifactRuntimeRepository
from lumi_api.image_edit.application import ImageEditApplicationService
from lumi_api.image_edit.model_gateway_adapter import to_model_request
from lumi_api.persistence.models_image_edit import ImageEditCostProjectionModel
from lumi_auto_repair import (
    AutoRepairJob,
    RepairCandidate,
    RepairCostEstimate,
    RepairPlan,
    RepairSideEffectUncertain,
)
from lumi_image_edit import (
    EditConstraint,
    EditIntent,
    GatewayEditRequest,
    ImageEditSpec,
    MaskSpec,
    ProtectedRegion,
    SourceImageRef,
)
from lumi_image_edit.planner import plan_edit
from lumi_model_gateway.gateway import ModelGateway


@dataclass(frozen=True, slots=True)
class RepairImageEditContext:
    source: SourceImageRef
    constraints: tuple[EditConstraint, ...]
    protected_regions: tuple[ProtectedRegion, ...]
    mask: MaskSpec
    code_git_sha: str
    brand_rule_set_version: str | None = None
    identity_requirement_ids: tuple[str, ...] = ()
    skill_versions: Mapping[str, str] | None = None
    seed: int | None = None


class RepairImageEditContextPort(Protocol):
    """Resolve NODE-45 assets + NODE-39/43/44 guards for one exact source."""

    def resolve(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> RepairImageEditContext: ...


class Node47LocalImageRepairBackend:
    """Use the existing NODE-47 pipeline; never bypass its auth/postflight/cost path."""

    def __init__(
        self,
        *,
        application: ImageEditApplicationService,
        model_gateway: ModelGateway,
        artifact_repository: ArtifactRuntimeRepository,
        session: Session,
        context: RepairImageEditContextPort,
    ) -> None:
        self.application = application
        self.model_gateway = model_gateway
        self.artifact_repository = artifact_repository
        self.session = session
        self.context = context

    async def estimate_local_edit(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> RepairCostEstimate:
        spec = self._spec(job=job, plan=plan, repair_branch_id=None)
        request = self._gateway_request(spec)
        decision = self.model_gateway.router.route(to_model_request(request))
        if not decision.candidates:
            raise ValueError("REPAIR_NODE47_NO_MODEL_ROUTE")
        candidate = decision.candidates[0]
        if candidate.estimate.amount_usd is None:
            raise ValueError("REPAIR_NODE47_UNKNOWN_COST_ROUTE_FORBIDDEN")
        return RepairCostEstimate(
            amount_usd=candidate.estimate.amount_usd,
            provider=candidate.model.provider,
            model=candidate.model.model,
            pricing_snapshot_id=candidate.estimate.pricing_snapshot_id,
        )

    async def execute_local_edit(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
    ) -> RepairCandidate:
        spec = self._spec(
            job=job,
            plan=plan,
            repair_branch_id=repair_branch_id,
        )
        edit = await self.application.submit(spec)
        if edit.status in {"AWAITING_MASK_APPROVAL", "AWAITING_CONFIRMATION"}:
            raise ValueError("REPAIR_NODE47_AUTOMATION_REQUIRES_PREAPPROVED_SAFE_MASK")
        if edit.status in {"QUEUED", "RUNNING"}:
            edit = await self.application.execute(
                organization_id=spec.organization_id,
                edit_id_value=edit.edit_id,
            )
        if edit.status == "PROVIDER_PENDING":
            edit = await self.application.resume_pending(
                organization_id=spec.organization_id,
                edit_id_value=edit.edit_id,
            )
        if edit.status == "PROVIDER_PENDING":
            raise RepairSideEffectUncertain(
                "REPAIR_NODE47_PROVIDER_PENDING",
                external_operation_id=edit.edit_id,
            )
        if edit.status != "COMPLETED" or edit.validation_decision != "PASS":
            raise ValueError(
                f"REPAIR_NODE47_EDIT_NOT_ACCEPTED:{edit.status}:{edit.validation_decision}"
            )
        if edit.result_artifact_version_id is None:
            raise ValueError("REPAIR_NODE47_RESULT_ARTIFACT_VERSION_REQUIRED")

        version = self.artifact_repository.get_version(
            UUID(edit.result_artifact_version_id)
        )
        if str(version.branch_id) != repair_branch_id:
            raise ValueError("REPAIR_NODE47_RESULT_ESCAPED_REPAIR_BRANCH")
        cost = self.session.get(ImageEditCostProjectionModel, UUID(edit.edit_id))
        if cost is None or cost.amount is None or cost.provider_request_id is None:
            raise RepairSideEffectUncertain(
                "REPAIR_NODE47_COST_PROJECTION_INCOMPLETE",
                external_operation_id=edit.edit_id,
            )
        return RepairCandidate(
            artifact_version_id=str(version.id),
            artifact_content_hash=version.content_hash,
            repair_branch_id=str(version.branch_id),
            actual_cost_usd=Decimal(cost.amount),
            provider=cost.provider,
            model=cost.model,
            provider_request_id=cost.provider_request_id,
            metadata={
                "node47_edit_id": edit.edit_id,
                "node47_route": edit.route,
                "pricing_snapshot_id": cost.pricing_snapshot_id,
                "monetary_owner": "NODE27_MODEL_GATEWAY_SETTLEMENT",
            },
        )

    def _spec(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str | None,
    ) -> ImageEditSpec:
        context = self.context.resolve(job=job, plan=plan)
        if context.source.artifact_version_id != job.working_source.artifact_version_id:
            raise ValueError("REPAIR_NODE47_SOURCE_VERSION_MISMATCH")
        if context.source.checksum_sha256 != job.working_source.artifact_content_hash:
            raise ValueError("REPAIR_NODE47_SOURCE_HASH_MISMATCH")
        instruction = self._instruction(plan)
        operation_id = str(
            uuid5(
                NAMESPACE_URL,
                f"lumi:auto-repair:node47:{job.job_id}:{plan.iteration}",
            )
        )
        return ImageEditSpec(
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            task_id=job.spec.task_id,
            operation_id=operation_id,
            source=context.source,
            intent=EditIntent(
                action="AUTO_REPAIR_REGION",
                instruction=instruction,
                allow_broad_change=False,
            ),
            constraints=context.constraints,
            protected_regions=context.protected_regions,
            mask=context.mask,
            brand_rule_set_version=context.brand_rule_set_version,
            identity_requirement_ids=context.identity_requirement_ids,
            budget_limit_usd=job.remaining_budget_usd,
            code_git_sha=context.code_git_sha,
            agent_version="auto-repair/1.0.0",
            recipe_version="auto-repair/1.0",
            skill_versions=context.skill_versions or {},
            seed=context.seed,
            target_branch_id=repair_branch_id,
        )

    @staticmethod
    def _instruction(plan: RepairPlan) -> str:
        parts: list[str] = []
        for directive in plan.directives:
            value = directive.parameters.get("instruction")
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
            else:
                parts.append(
                    f"Repair {directive.dimension} issue {directive.source_violation_id} "
                    f"inside the editable mask only. Preserve all protected regions exactly."
                )
        return "\n".join(parts)

    @staticmethod
    def _gateway_request(spec: ImageEditSpec) -> GatewayEditRequest:
        plan = plan_edit(spec)
        if not plan.requires_provider:
            raise ValueError("REPAIR_NODE47_PROVIDER_ROUTE_REQUIRED")
        return GatewayEditRequest(
            spec.organization_id,
            spec.project_id,
            spec.task_id,
            spec.operation_id,
            str(
                uuid5(
                    NAMESPACE_URL,
                    f"{spec.organization_id}:{spec.operation_id}:{spec.semantic_hash}",
                )
            ),
            plan.route,
            spec.source.durable_ref,
            spec.mask.durable_ref if spec.mask else None,
            spec.intent.instruction,
            plan.required_capabilities,
            spec.protected_regions,
            (),
            spec.budget_limit_usd,
            spec.seed,
        )
