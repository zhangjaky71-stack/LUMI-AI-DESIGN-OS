from __future__ import annotations

import json
from uuid import UUID

from lumi_image_generation import (
    GatewayEstimate,
    GatewayRequest,
    GatewayResult,
    GatewayStatus,
    GenerationMode,
    ProviderOutputRef,
)
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

_MODE_CAPABILITY = {
    GenerationMode.TEXT_TO_IMAGE: Capability.IMAGE_GENERATE,
    GenerationMode.REFERENCE_TO_IMAGE: Capability.IMAGE_REFERENCE_CONSISTENCY,
    GenerationMode.PRODUCT_SCENE: Capability.IMAGE_REFERENCE_CONSISTENCY,
    GenerationMode.STYLE_REFERENCE: Capability.IMAGE_REFERENCE_CONSISTENCY,
    GenerationMode.TRANSPARENT_ASSET: Capability.IMAGE_TRANSPARENT_BACKGROUND,
    GenerationMode.BACKGROUND_GENERATION: Capability.IMAGE_GENERATE,
    GenerationMode.COMPOSITION_EXPLORATION: Capability.IMAGE_GENERATE,
}
_STATUS = {
    ResultStatus.COMPLETED: GatewayStatus.COMPLETED,
    ResultStatus.PENDING: GatewayStatus.PENDING,
    ResultStatus.FAILED: GatewayStatus.FAILED,
    ResultStatus.CANCELLED: GatewayStatus.CANCELLED,
}


def _quality(value: str) -> QualityProfile:
    return QualityProfile(value.casefold())


def _prompt_payload(request: GatewayRequest) -> str:
    value = {
        "generation_mode": request.mode.value,
        "variant_index": request.variant_index,
        "prompt_blocks": {
            "objective": request.prompt.objective,
            "content": request.prompt.content,
            "visual_direction": request.prompt.visual_direction,
            "brand_constraints": list(request.prompt.brand_constraints),
            "identity_requirements": list(request.prompt.identity_requirements),
            "negative_constraints": list(request.prompt.negative_constraints),
            "output_dimensions": request.prompt.output_dimensions,
            "template_version": request.prompt.template_version,
        },
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _constraints(request: GatewayRequest) -> dict[str, object]:
    return {
        "generation_mode": request.mode.value,
        "variant_index": request.variant_index,
        "target_width": request.target_width,
        "target_height": request.target_height,
        "output_format": request.output_requirements.format.value.lower(),
        "transparent_background": request.output_requirements.transparent_background,
        "seed": request.seed,
        "items": [
            {
                "constraint_id": item.constraint_id,
                "type": item.constraint_type,
                "severity": item.severity.value,
                "snapshot_hash": item.snapshot_hash,
                "parameters": dict(item.parameters),
            }
            for item in request.constraints
        ],
    }


def to_model_request(request: GatewayRequest) -> ModelRequest:
    return ModelRequest(
        request_id=request.request_id,
        organization_id=request.organization_id,
        operation_id=request.variant_operation_id,
        capability=_MODE_CAPABILITY[request.mode],
        inputs=(
            ModelInput(
                kind=InputKind.TEXT,
                role="user",
                text=_prompt_payload(request),
            ),
        ),
        quality_profile=_quality(request.quality_profile.value),
        latency_profile=LatencyProfile.INTERACTIVE,
        budget_limit=request.budget_limit_usd,
        project_id=request.project_id,
        task_id=request.task_id,
        agent_run_id=request.agent_run_id,
        generation_id=request.generation_id,
        reference_assets=tuple(item.durable_ref for item in request.references),
        constraints=_constraints(request),
        routing_hints=RoutingHints(allow_fallback=True),
    )


def _outputs(result) -> tuple[ProviderOutputRef, ...]:
    values: list[ProviderOutputRef] = []
    for output in result.outputs:
        if output.kind != "asset" or not output.asset_ref:
            raise ValueError("IMAGE_GATEWAY_OUTPUT_MUST_BE_ASSET_REF")
        values.append(ProviderOutputRef(output.asset_ref))
    return tuple(values)


def _candidate(decision, provider: str, model: str):
    return next(
        (
            (index, item)
            for index, item in enumerate(decision.candidates)
            if item.model.provider == provider and item.model.model == model
        ),
        None,
    )


def _result(result, decision, request: GatewayRequest) -> GatewayResult:
    matching = _candidate(decision, result.provider, result.model)
    if matching is None:
        revision = registry = None
        reasons = ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
    else:
        index, candidate = matching
        revision = candidate.model.model_revision_id
        registry = candidate.model.registry_snapshot_id
        reasons = candidate.reason_codes
        if index:
            reasons += (f"FALLBACK_INDEX:{index}",)
    return GatewayResult(
        status=_STATUS[result.status],
        provider=result.provider,
        model=result.model,
        outputs=_outputs(result),
        provider_request_id=result.provider_request_id,
        model_revision=revision,
        registry_snapshot_id=registry,
        cost_usd=result.cost.amount_usd,
        cost_confidence=result.cost.confidence.value,
        pricing_snapshot_id=result.cost.pricing_snapshot_id,
        routing_reason_codes=reasons,
        safety_metadata=result.safety_metadata,
        finish_reason=result.finish_reason,
        seed=request.seed,
    )


class ModelGatewayImageAdapter:
    """NODE-46 speaks only the current provider-neutral NODE-22 contract."""

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def estimate(self, request: GatewayRequest) -> GatewayEstimate:
        model_request = to_model_request(request)
        decision = self.gateway.router.route(model_request)
        if not decision.candidates:
            raise ValueError("GENERATION_NO_MODEL_ROUTE")
        candidate = decision.candidates[0]
        amount = candidate.estimate.amount_usd
        if amount is None:
            raise ValueError("GENERATION_PROVIDER_COST_ESTIMATE_REQUIRED")
        return GatewayEstimate(
            amount_usd=amount,
            pricing_snapshot_id=candidate.estimate.pricing_snapshot_id,
            provider=candidate.model.provider,
            model=candidate.model.model,
            model_revision=candidate.model.model_revision_id,
            registry_snapshot_id=candidate.model.registry_snapshot_id,
            routing_reason_codes=candidate.reason_codes,
        )

    async def invoke(self, request: GatewayRequest) -> GatewayResult:
        model_request = to_model_request(request)
        decision = self.gateway.router.route(model_request)
        result = await self.gateway.invoke(model_request)
        return _result(result, decision, request)

    async def poll(
        self,
        *,
        request: GatewayRequest,
        pending_result: GatewayResult,
    ) -> GatewayResult:
        if not pending_result.provider_request_id:
            raise ValueError("GENERATION_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        result = await self.gateway.get_async_status(
            provider=pending_result.provider,
            model=pending_result.model,
            provider_request_id=pending_result.provider_request_id,
            capability=_MODE_CAPABILITY[request.mode],
        )
        if result.provider != pending_result.provider or result.model != pending_result.model:
            raise ValueError("GENERATION_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return GatewayResult(
            status=_STATUS[result.status],
            provider=result.provider,
            model=result.model,
            outputs=_outputs(result),
            provider_request_id=result.provider_request_id,
            model_revision=pending_result.model_revision,
            registry_snapshot_id=pending_result.registry_snapshot_id,
            cost_usd=result.cost.amount_usd,
            cost_confidence=result.cost.confidence.value,
            pricing_snapshot_id=result.cost.pricing_snapshot_id,
            routing_reason_codes=pending_result.routing_reason_codes,
            safety_metadata=result.safety_metadata,
            finish_reason=result.finish_reason,
            seed=request.seed,
        )

    async def cancel(
        self,
        *,
        request: GatewayRequest,
        pending_result: GatewayResult,
    ) -> bool:
        del request
        if not pending_result.provider_request_id:
            return False
        return await self.gateway.cancel(
            provider=pending_result.provider,
            model=pending_result.model,
            provider_request_id=pending_result.provider_request_id,
        )
