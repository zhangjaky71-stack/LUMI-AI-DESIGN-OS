from __future__ import annotations

import json
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_image_edit import GatewayEditRequest, GatewayEditResult
from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.models import (
    Capability,
    InputKind,
    LatencyProfile,
    ModelInput,
    ModelRequest,
    QualityProfile,
    ResultStatus,
    RoutingHints,
)

_STATUS = {
    ResultStatus.COMPLETED: "SUCCEEDED",
    ResultStatus.PENDING: "PENDING",
    ResultStatus.FAILED: "FAILED",
    ResultStatus.CANCELLED: "CANCELLED",
}


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


def _primary(request: GatewayEditRequest) -> Capability:
    if request.route == "FULL_IMAGE_EDIT":
        return Capability.IMAGE_EDIT
    return Capability.IMAGE_MASK_EDIT


def _prompt_payload(request: GatewayEditRequest) -> str:
    value = {
        "edit_id": request.edit_id,
        "route": request.route,
        "instruction": request.instruction,
        "protected_regions": [
            {
                "id": region.region_id,
                "role": region.role,
                "severity": region.severity,
                "rect": [
                    region.rect.x,
                    region.rect.y,
                    region.rect.width,
                    region.rect.height,
                ],
            }
            for region in request.protected_regions
        ],
    }
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def to_model_request(request: GatewayEditRequest) -> ModelRequest:
    references = [request.source_ref]
    if request.mask_ref:
        references.append(request.mask_ref)
    references.extend(request.reference_asset_refs)
    inputs = (
        ModelInput(
            kind=InputKind.TEXT,
            role="user",
            text=_prompt_payload(request),
        ),
        ModelInput(
            kind=InputKind.IMAGE,
            role="user",
            uri=request.source_ref,
            media_type="image/*",
        ),
    )
    return ModelRequest(
        request_id=_uuid(request.edit_id),
        organization_id=_uuid(request.organization_id),
        operation_id=_uuid(request.operation_id),
        capability=_primary(request),
        inputs=inputs,
        quality_profile=QualityProfile.HIGH,
        latency_profile=LatencyProfile.INTERACTIVE,
        budget_limit=request.budget_limit_usd,
        project_id=_uuid(request.project_id),
        task_id=_uuid(request.task_id),
        reference_assets=tuple(references),
        constraints={
            "required_capabilities": list(request.required_capabilities),
            "mask_ref": request.mask_ref,
            "protected_region_count": len(request.protected_regions),
            "seed": request.seed,
        },
        routing_hints=RoutingHints(allow_fallback=True),
    )


def _single_asset_ref(result) -> str | None:
    if result.status is not ResultStatus.COMPLETED:
        return None
    assets = tuple(
        output.asset_ref
        for output in result.outputs
        if output.kind == "asset" and output.asset_ref
    )
    if len(assets) != 1:
        raise ValueError("IMAGE_EDIT_GATEWAY_REQUIRES_SINGLE_ASSET_OUTPUT")
    return assets[0]


def _convert(result, decision, request: GatewayEditRequest) -> GatewayEditResult:
    matching = next(
        (
            (index, candidate)
            for index, candidate in enumerate(decision.candidates)
            if candidate.model.provider == result.provider
            and candidate.model.model == result.model
        ),
        None,
    )
    if matching is None:
        reasons = ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        revision = None
        registry_snapshot_id = None
    else:
        index, candidate = matching
        reasons = candidate.reason_codes
        if index:
            reasons += (f"FALLBACK_INDEX:{index}",)
        revision = candidate.model.model_revision_id
        registry_snapshot_id = candidate.model.registry_snapshot_id
    return GatewayEditResult(
        _STATUS[result.status],
        result.provider,
        result.model,
        result.provider_request_id,
        _single_asset_ref(result),
        None,
        result.cost.amount_usd,
        result.cost.confidence.value,
        result.cost.pricing_snapshot_id,
        reasons,
        result.safety_metadata,
        revision,
        registry_snapshot_id,
        request.seed,
        result.finish_reason,
    )


class ModelGatewayImageEditAdapter:
    """NODE-47 uses current NODE-22 routing, paid-idempotency and cost settlement."""

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def invoke(self, request: GatewayEditRequest) -> GatewayEditResult:
        model_request = to_model_request(request)
        decision = self.gateway.router.route(model_request)
        if not decision.candidates:
            raise ValueError("IMAGE_EDIT_NO_MODEL_ROUTE")
        result = await self.gateway.invoke(model_request)
        return _convert(result, decision, request)

    async def poll(
        self,
        request: GatewayEditRequest,
        pending: GatewayEditResult,
    ) -> GatewayEditResult:
        if not pending.provider_request_id:
            raise ValueError("IMAGE_EDIT_PENDING_PROVIDER_REQUEST_REQUIRED")
        result = await self.gateway.get_async_status(
            provider=pending.provider,
            model=pending.model,
            provider_request_id=pending.provider_request_id,
            capability=_primary(request),
        )
        if result.provider != pending.provider or result.model != pending.model:
            raise ValueError("IMAGE_EDIT_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return GatewayEditResult(
            _STATUS[result.status],
            result.provider,
            result.model,
            result.provider_request_id,
            _single_asset_ref(result),
            None,
            result.cost.amount_usd,
            result.cost.confidence.value,
            result.cost.pricing_snapshot_id,
            pending.routing_reason_codes,
            result.safety_metadata,
            pending.model_revision,
            pending.registry_snapshot_id,
            request.seed,
            result.finish_reason,
        )

    async def cancel(self, pending: GatewayEditResult) -> bool:
        if not pending.provider_request_id:
            return False
        return await self.gateway.cancel(
            provider=pending.provider,
            model=pending.model,
            provider_request_id=pending.provider_request_id,
        )
