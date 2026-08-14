from __future__ import annotations

import hashlib
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.models import (
    Capability,
    LatencyProfile,
    ModelRequest,
    ModelResult,
    QualityProfile,
    ResultStatus,
)

from .model import CompiledShot, GatewayEstimate, GatewayVideoResult, ProviderJobRecord, VideoTaskSpec


def _stable_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


def _capability(shot: CompiledShot, continuity_refs: tuple[str, ...]) -> Capability:
    return Capability.VIDEO_IMAGE_TO_VIDEO if shot.shot.source_ref is not None or continuity_refs else Capability.VIDEO_TEXT_TO_VIDEO


def _required_features(shot: CompiledShot, continuity_refs: tuple[str, ...]) -> list[str]:
    required: list[str] = []
    if shot.shot.source_ref is not None:
        required.append("video.start_frame")
    if continuity_refs:
        required.append("video.reference_image")
    if shot.shot.camera_motion:
        required.append("video.camera_controls")
    return required


def to_model_request(spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> ModelRequest:
    refs: list[str] = []
    if shot.shot.source_ref is not None:
        refs.append(shot.shot.source_ref.durable_ref)
    refs.extend(continuity_refs)
    inputs: dict[str, Any] = {
        "prompt": shot.shot.prompt,
        "negative_prompt": spec.negative_prompt,
        "duration_seconds": format(shot.shot.duration_seconds, "f"),
        "width": spec.width,
        "height": spec.height,
        "fps": spec.fps,
        "camera_motion": shot.shot.camera_motion,
        "subject_action": shot.shot.subject_action,
        "seed": spec.seed,
    }
    return ModelRequest(
        organization_id=_stable_uuid(spec.organization_id),
        project_id=_stable_uuid(spec.project_id),
        task_id=_stable_uuid(spec.task_id),
        agent_run_id=_stable_uuid(spec.agent_run_id) if spec.agent_run_id else None,
        operation_id=_stable_uuid(shot.paid_operation_id),
        generation_id=_stable_uuid(f"video:{spec.operation_id}"),
        capability=_capability(shot, continuity_refs),
        quality_profile=QualityProfile.HIGH,
        latency_profile=LatencyProfile.BATCH,
        budget_limit_usd=spec.budget_limit_usd,
        inputs=inputs,
        reference_assets=tuple(refs),
        constraints={
            "duration_seconds": format(shot.shot.duration_seconds, "f"),
            "width": spec.width,
            "height": spec.height,
            "fps": spec.fps,
            "required_features": _required_features(shot, continuity_refs),
        },
        routing_hints={"allow_fallback": True},
    )


def _status(status: ResultStatus) -> str:
    return status.value.upper()


def _normalize(result: ModelResult, routing_reason_codes: tuple[str, ...]) -> GatewayVideoResult:
    output_ref: str | None = None
    output_mime: str | None = None
    if result.status == ResultStatus.SUCCEEDED:
        if len(result.outputs) != 1:
            raise ValueError("VIDEO_GATEWAY_OUTPUT_COUNT_INVALID")
        output = result.outputs[0]
        if output.kind != "asset_ref" or not isinstance(output.value, str):
            raise ValueError("VIDEO_GATEWAY_OUTPUT_MUST_BE_ASSET_REF")
        output_ref = output.value
        output_mime = output.mime_type
    return GatewayVideoResult(
        status=cast(Any, _status(result.status)),
        provider=result.provider,
        model=result.model,
        provider_request_id=result.provider_request_id,
        output_ref=output_ref,
        output_mime_type=output_mime,
        cost_usd=result.cost.amount_usd,
        cost_confidence=result.cost.confidence.value,
        pricing_snapshot_id=result.cost.price_snapshot_id,
        routing_reason_codes=routing_reason_codes,
        safety_metadata=result.safety_metadata,
        finish_reason=result.finish_reason,
    )


class ModelGatewayVideoAdapter:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def estimate(self, *, spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> GatewayEstimate:
        request = to_model_request(spec, shot, continuity_refs)
        decision = await self.gateway.router.route(request)
        candidate = decision.candidates[0]
        if candidate.estimate.amount_usd is None:
            raise ValueError("VIDEO_PROVIDER_COST_ESTIMATE_REQUIRED")
        return GatewayEstimate(
            amount_usd=candidate.estimate.amount_usd,
            provider=candidate.provider,
            model=candidate.model,
            pricing_snapshot_id=candidate.estimate.price_snapshot_id,
            routing_reason_codes=candidate.reason_codes,
        )

    async def submit(self, *, spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> GatewayVideoResult:
        request = to_model_request(spec, shot, continuity_refs)
        decision = await self.gateway.router.route(request)
        result = await self.gateway.invoke(request)
        matching = next(
            ((index, item) for index, item in enumerate(decision.candidates) if item.provider == result.provider and item.model == result.model),
            None,
        )
        if matching is None:
            reasons = ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        else:
            index, item = matching
            reasons = item.reason_codes + ((f"FALLBACK_INDEX:{index}",) if index else ())
        return _normalize(result, reasons)

    async def poll(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        request_id = pending.result.provider_request_id
        if not request_id:
            raise ValueError("VIDEO_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        result = await self.gateway.get_async_status(
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=request_id,
        )
        if result.provider != pending.result.provider or result.model != pending.result.model:
            raise ValueError("VIDEO_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return _normalize(result, pending.result.routing_reason_codes)

    async def cancel(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        request_id = pending.result.provider_request_id
        if not request_id:
            raise ValueError("VIDEO_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        result = await self.gateway.cancel(
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=request_id,
        )
        return _normalize(result, pending.result.routing_reason_codes)


def request_hash(spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> str:
    return hashlib.sha256(to_model_request(spec, shot, continuity_refs).semantic_hash.encode()).hexdigest()
