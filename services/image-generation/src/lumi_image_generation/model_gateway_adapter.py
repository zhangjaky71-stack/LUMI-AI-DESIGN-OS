from __future__ import annotations

from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.models import (
    Capability,
    LatencyProfile,
    ModelRequest,
    ModelResult,
    QualityProfile as GatewayQualityProfile,
    ResultStatus,
)

from .model import (
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GatewayResultStatus,
    GenerationMode,
    ProviderOutputRef,
)
from .ports import GatewayEstimate

_MODE_CAPABILITY: dict[GenerationMode, Capability] = {
    "TEXT_TO_IMAGE": Capability.IMAGE_GENERATE,
    "REFERENCE_TO_IMAGE": Capability.IMAGE_REFERENCE_CONSISTENCY,
    "PRODUCT_SCENE": Capability.IMAGE_REFERENCE_CONSISTENCY,
    "STYLE_REFERENCE": Capability.IMAGE_REFERENCE_CONSISTENCY,
    "TRANSPARENT_ASSET": Capability.IMAGE_TRANSPARENT_BACKGROUND,
    "BACKGROUND_GENERATION": Capability.IMAGE_GENERATE,
    "COMPOSITION_EXPLORATION": Capability.IMAGE_GENERATE,
}


def _stable_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


def _quality(value: str) -> GatewayQualityProfile:
    return GatewayQualityProfile(value.casefold())


def _constraint_payload(request: GatewayGenerationRequest) -> dict[str, Any]:
    return {
        "items": [
            {
                "constraint_id": item.constraint_id,
                "type": item.constraint_type,
                "severity": item.severity,
                "snapshot_hash": item.snapshot_hash,
                "parameters": dict(item.parameters),
            }
            for item in request.constraints
        ],
        "target_width": request.target_width,
        "target_height": request.target_height,
        "transparent_background": request.output_requirements.transparent_background,
        "output_format": request.output_requirements.format,
    }


def to_model_request(request: GatewayGenerationRequest) -> ModelRequest:
    capability = _MODE_CAPABILITY[request.mode]
    inputs: dict[str, Any] = {
        "generation_mode": request.mode,
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
        "width": request.target_width,
        "height": request.target_height,
        "format": request.output_requirements.format.lower(),
        "transparent_background": request.output_requirements.transparent_background,
        "seed": request.seed,
    }
    return ModelRequest(
        organization_id=UUID(request.organization_id),
        project_id=UUID(request.project_id),
        task_id=UUID(request.task_id),
        operation_id=UUID(request.variant_operation_id),
        generation_id=_stable_uuid(request.generation_id),
        agent_run_id=_stable_uuid(request.agent_run_id) if request.agent_run_id else None,
        capability=capability,
        quality_profile=_quality(request.quality_profile),
        latency_profile=LatencyProfile.INTERACTIVE,
        budget_limit_usd=request.budget_limit_usd,
        inputs=inputs,
        reference_assets=tuple(reference.durable_ref for reference in request.references),
        constraints=_constraint_payload(request),
        routing_hints={"allow_fallback": True},
    )


def _normalize_outputs(result: ModelResult) -> tuple[ProviderOutputRef, ...]:
    outputs: list[ProviderOutputRef] = []
    for output in result.outputs:
        if output.kind != "asset_ref" or not isinstance(output.value, str):
            raise ValueError("IMAGE_GATEWAY_OUTPUT_MUST_BE_ASSET_REF")
        outputs.append(ProviderOutputRef(ref=output.value, mime_type=output.mime_type))
    return tuple(outputs)


def _status(value: ResultStatus) -> GatewayResultStatus:
    return cast(GatewayResultStatus, value.value.upper())


class ModelGatewayImageAdapter:
    """NODE-46 adapter. Provider-native payloads remain inside NODE-22 adapters."""

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def estimate(self, request: GatewayGenerationRequest) -> GatewayEstimate:
        model_request = to_model_request(request)
        decision = await self.gateway.router.route(model_request)
        candidate = decision.candidates[0]
        amount = candidate.estimate.amount_usd
        if amount is None:
            raise ValueError("GENERATION_PROVIDER_COST_ESTIMATE_REQUIRED")
        return GatewayEstimate(
            amount_usd=amount,
            pricing_snapshot_id=candidate.estimate.price_snapshot_id,
            provider=candidate.provider,
            model=candidate.model,
            routing_reason_codes=candidate.reason_codes,
        )

    async def invoke(self, request: GatewayGenerationRequest) -> GatewayGenerationResult:
        model_request = to_model_request(request)
        decision = await self.gateway.router.route(model_request)
        result = await self.gateway.invoke(model_request)
        matching = next(
            (
                (index, candidate)
                for index, candidate in enumerate(decision.candidates)
                if candidate.provider == result.provider and candidate.model == result.model
            ),
            None,
        )
        reasons: tuple[str, ...]
        if matching is None:
            reasons = ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        else:
            index, candidate = matching
            reasons = candidate.reason_codes + ((f"FALLBACK_INDEX:{index}",) if index else ())
        return GatewayGenerationResult(
            status=_status(result.status),
            provider=result.provider,
            model=result.model,
            model_revision=None,
            provider_request_id=result.provider_request_id,
            outputs=_normalize_outputs(result),
            cost_usd=result.cost.amount_usd,
            cost_confidence=result.cost.confidence.value,
            pricing_snapshot_id=result.cost.price_snapshot_id,
            routing_reason_codes=reasons,
            safety_metadata=result.safety_metadata,
            finish_reason=result.finish_reason,
            seed=request.seed,
        )

    async def poll(
        self,
        *,
        request: GatewayGenerationRequest,
        pending_result: GatewayGenerationResult,
    ) -> GatewayGenerationResult:
        provider_request_id = pending_result.provider_request_id
        if not provider_request_id:
            raise ValueError("GENERATION_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        adapter = self.gateway.registry.get(pending_result.provider, pending_result.model)
        result = await adapter.get_async_status(provider_request_id)
        if result.provider != pending_result.provider or result.model != pending_result.model:
            raise ValueError("GENERATION_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return GatewayGenerationResult(
            status=_status(result.status),
            provider=result.provider,
            model=result.model,
            model_revision=pending_result.model_revision,
            provider_request_id=result.provider_request_id,
            outputs=_normalize_outputs(result),
            cost_usd=result.cost.amount_usd,
            cost_confidence=result.cost.confidence.value,
            pricing_snapshot_id=result.cost.price_snapshot_id,
            routing_reason_codes=pending_result.routing_reason_codes,
            safety_metadata=result.safety_metadata,
            finish_reason=result.finish_reason,
            seed=request.seed,
        )
