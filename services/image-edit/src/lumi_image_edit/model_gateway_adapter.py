from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_model_gateway import (
    Capability,
    LatencyProfile,
    ModelGateway,
    ModelRequest,
    QualityProfile,
    ResultStatus,
)

from .model import EditPlan, GatewayEditResult, ImageEditSpec, MaskSpec


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


def _capability(plan: EditPlan) -> Capability:
    return Capability.IMAGE_MASK_EDIT if plan.requires_mask else Capability.IMAGE_EDIT


def _request(spec: ImageEditSpec, plan: EditPlan, mask: MaskSpec | None) -> ModelRequest:
    if plan.requires_mask and mask is None:
        raise ValueError("IMAGE_EDIT_PROVIDER_MASK_REQUIRED")
    required_capabilities = []
    if spec.protected_regions or spec.identity_requirement_ids:
        required_capabilities.append(Capability.IMAGE_REFERENCE_CONSISTENCY.value)
    inputs: dict[str, Any] = {
        "edit_route": plan.route,
        "instruction": spec.intent.instruction,
        "source_ref": spec.source.durable_ref,
        "source_asset_version": spec.source.asset_version,
        "source_checksum_sha256": spec.source.checksum_sha256,
        "width": spec.source.width,
        "height": spec.source.height,
        "mask_ref": mask.durable_ref if mask else None,
        "mask_checksum_sha256": mask.checksum_sha256 if mask else None,
        "protected_regions": [
            {
                "region_id": region.region_id,
                "role": region.role,
                "rect": {
                    "x": region.rect.x,
                    "y": region.rect.y,
                    "width": region.rect.width,
                    "height": region.rect.height,
                },
            }
            for region in spec.protected_regions
        ],
    }
    return ModelRequest(
        organization_id=_uuid(spec.organization_id),
        project_id=_uuid(spec.project_id),
        task_id=_uuid(spec.task_id),
        operation_id=_uuid(spec.operation_id),
        agent_run_id=_uuid(spec.agent_run_id) if spec.agent_run_id else None,
        capability=_capability(plan),
        quality_profile=QualityProfile.HIGH,
        latency_profile=LatencyProfile.INTERACTIVE,
        budget_limit_usd=spec.budget_limit_usd,
        inputs=inputs,
        reference_assets=tuple(
            [spec.source.durable_ref] + ([mask.durable_ref] if mask is not None else [])
        ),
        constraints={
            "required_capabilities": required_capabilities,
            "protected_regions": [region.region_id for region in spec.protected_regions],
            "identity_requirement_ids": list(spec.identity_requirement_ids),
        },
        routing_hints={"allow_fallback": True},
    )


def _normalize(result: object, *, seed: int | None) -> GatewayEditResult:
    from lumi_model_gateway import ModelResult

    if not isinstance(result, ModelResult):
        raise TypeError("IMAGE_EDIT_MODEL_RESULT_INVALID")
    output_ref: str | None = None
    output_mime: str | None = None
    if result.status == ResultStatus.SUCCEEDED:
        if len(result.outputs) != 1 or result.outputs[0].kind != "asset_ref":
            raise ValueError("IMAGE_EDIT_GATEWAY_OUTPUT_INVALID")
        value = result.outputs[0].value
        if not isinstance(value, str):
            raise ValueError("IMAGE_EDIT_GATEWAY_ASSET_REF_INVALID")
        output_ref = value
        output_mime = result.outputs[0].mime_type
    return GatewayEditResult(
        status=result.status.value.upper(),  # type: ignore[arg-type]
        provider=result.provider,
        model=result.model,
        provider_request_id=result.provider_request_id,
        output_ref=output_ref,
        output_mime_type=output_mime,
        cost_usd=result.cost.amount_usd,
        cost_confidence=result.cost.confidence.value,
        pricing_snapshot_id=result.cost.price_snapshot_id,
        routing_reason_codes=(),
        safety_metadata=result.safety_metadata,
        seed=seed,
    )


class ModelGatewayImageEditAdapter:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def invoke(
        self, *, spec: ImageEditSpec, plan: EditPlan, mask: MaskSpec | None
    ) -> GatewayEditResult:
        request = _request(spec, plan, mask)
        decision = await self.gateway.router.route(request)
        result = await self.gateway.invoke(request)
        match = next(
            (candidate for candidate in decision.candidates if candidate.provider == result.provider and candidate.model == result.model),
            None,
        )
        normalized = _normalize(result, seed=spec.seed)
        reasons = match.reason_codes if match is not None else ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        return GatewayEditResult(
            status=normalized.status,
            provider=normalized.provider,
            model=normalized.model,
            provider_request_id=normalized.provider_request_id,
            output_ref=normalized.output_ref,
            output_mime_type=normalized.output_mime_type,
            cost_usd=normalized.cost_usd,
            cost_confidence=normalized.cost_confidence,
            pricing_snapshot_id=normalized.pricing_snapshot_id,
            routing_reason_codes=reasons,
            safety_metadata=normalized.safety_metadata,
            seed=normalized.seed,
        )

    async def poll(
        self,
        *,
        spec: ImageEditSpec,
        plan: EditPlan,
        pending: GatewayEditResult,
        mask: MaskSpec | None,
    ) -> GatewayEditResult:
        del plan, mask
        if not pending.provider_request_id:
            raise ValueError("IMAGE_EDIT_PENDING_REQUEST_ID_REQUIRED")
        adapter = self.gateway.registry.get(pending.provider, pending.model)
        result = await adapter.get_async_status(pending.provider_request_id)
        if result.provider != pending.provider or result.model != pending.model:
            raise ValueError("IMAGE_EDIT_ASYNC_PROVIDER_CHANGED")
        normalized = _normalize(result, seed=spec.seed)
        return GatewayEditResult(
            status=normalized.status,
            provider=normalized.provider,
            model=normalized.model,
            provider_request_id=normalized.provider_request_id,
            output_ref=normalized.output_ref,
            output_mime_type=normalized.output_mime_type,
            cost_usd=normalized.cost_usd,
            cost_confidence=normalized.cost_confidence,
            pricing_snapshot_id=normalized.pricing_snapshot_id,
            routing_reason_codes=pending.routing_reason_codes,
            safety_metadata=normalized.safety_metadata,
            seed=normalized.seed,
        )
