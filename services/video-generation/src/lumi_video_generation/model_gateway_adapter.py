from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.models import (
    Capability,
    InputKind,
    LatencyProfile,
    ModelInput,
    ModelRequest,
    NormalizedResult,
    QualityProfile,
    ResultStatus,
    RoutingHints,
)

from .model import (
    CompiledShot,
    GatewayEstimate,
    GatewayVideoResult,
    ProviderJobRecord,
    VideoTaskSpec,
)


def _stable_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


def _capability(shot: CompiledShot) -> Capability:
    if shot.shot.source_ref is not None or shot.continuity_refs:
        return Capability.VIDEO_IMAGE_TO_VIDEO
    return Capability.VIDEO_TEXT_TO_VIDEO


def _required_features(shot: CompiledShot) -> frozenset[str]:
    required = set(shot.shot.required_features)
    if shot.shot.source_ref is not None:
        required.add("video.start_frame")
    if shot.continuity_refs:
        required.add("video.reference_image")
    if shot.shot.camera_motion:
        required.add("video.camera_controls")
    return frozenset(required)


@dataclass(frozen=True, slots=True)
class VideoFeatureRegistry:
    snapshot_id: str
    provider_features: dict[str, frozenset[str]]

    def excluded_providers(self, required: frozenset[str]) -> tuple[str, ...]:
        if not required:
            return ()
        eligible = {
            provider
            for provider, features in self.provider_features.items()
            if required <= features
        }
        if not eligible:
            raise ValueError("VIDEO_REQUIRED_PROVIDER_FEATURES_UNAVAILABLE")
        return tuple(
            sorted(provider for provider in self.provider_features if provider not in eligible)
        )


def _shot_budget(spec: VideoTaskSpec) -> Decimal | None:
    if spec.budget_limit_usd is None:
        return None
    return spec.budget_limit_usd / Decimal(len(spec.shots))


def to_model_request(
    spec: VideoTaskSpec,
    shot: CompiledShot,
    *,
    feature_registry: VideoFeatureRegistry | None = None,
    excluded_provider_keys: tuple[str, ...] = (),
) -> ModelRequest:
    required_features = _required_features(shot)
    registry_excluded: tuple[str, ...] = ()
    if required_features:
        if feature_registry is None:
            raise ValueError("VIDEO_PROVIDER_FEATURE_REGISTRY_REQUIRED")
        registry_excluded = feature_registry.excluded_providers(required_features)
    excluded = tuple(sorted(set(registry_excluded) | set(excluded_provider_keys)))

    references: list[str] = []
    if shot.shot.source_ref is not None:
        references.append(shot.shot.source_ref.durable_ref)
    references.extend(shot.continuity_refs)

    prompt_parts = [shot.shot.prompt]
    if spec.negative_prompt:
        prompt_parts.append(f"Negative: {spec.negative_prompt}")
    if shot.shot.camera_motion:
        prompt_parts.append(f"Camera: {shot.shot.camera_motion}")
    if shot.shot.subject_action:
        prompt_parts.append(f"Action: {shot.shot.subject_action}")

    constraints = {
        "duration_seconds": format(shot.shot.duration_seconds, "f"),
        "width": spec.width,
        "height": spec.height,
        "fps": spec.fps,
        "seed": spec.seed,
        "video_required_features": sorted(required_features),
        "video_feature_registry_snapshot_id": (
            feature_registry.snapshot_id if feature_registry is not None else None
        ),
    }
    return ModelRequest(
        request_id=_stable_uuid(f"video-request:{shot.paid_operation_id}"),
        organization_id=_stable_uuid(spec.organization_id),
        project_id=_stable_uuid(spec.project_id),
        task_id=_stable_uuid(spec.task_id),
        agent_run_id=_stable_uuid(spec.agent_run_id) if spec.agent_run_id else None,
        operation_id=_stable_uuid(shot.paid_operation_id),
        generation_id=_stable_uuid(f"video-generation:{spec.operation_id}"),
        capability=_capability(shot),
        inputs=(
            ModelInput(
                kind=InputKind.TEXT,
                role="user",
                text="\n".join(prompt_parts),
            ),
        ),
        quality_profile=QualityProfile.HIGH,
        latency_profile=LatencyProfile.BATCH,
        budget_limit=_shot_budget(spec),
        reference_assets=tuple(references),
        constraints=constraints,
        routing_hints=RoutingHints(
            excluded_providers=excluded,
            allow_fallback=True,
            allow_unknown_cost=False,
        ),
    )


def _normalize(result: NormalizedResult, reasons: tuple[str, ...]) -> GatewayVideoResult:
    output_ref: str | None = None
    output_mime: str | None = None
    if result.status is ResultStatus.COMPLETED:
        if len(result.outputs) != 1:
            raise ValueError("VIDEO_GATEWAY_OUTPUT_COUNT_INVALID")
        output = result.outputs[0]
        if not output.asset_ref:
            raise ValueError("VIDEO_GATEWAY_OUTPUT_MUST_BE_ASSET_REF")
        output_ref = output.asset_ref
    return GatewayVideoResult(
        status=result.status.value.upper(),
        provider=result.provider,
        model=result.model,
        provider_request_id=result.provider_request_id,
        output_ref=output_ref,
        output_mime_type=output_mime,
        cost_usd=result.cost.amount_usd,
        pricing_snapshot_id=result.cost.pricing_snapshot_id,
        routing_reason_codes=reasons,
        safety_metadata=result.safety_metadata,
        finish_reason=result.finish_reason,
    )


class ModelGatewayVideoAdapter:
    def __init__(
        self,
        gateway: ModelGateway,
        *,
        feature_registry: VideoFeatureRegistry | None = None,
    ) -> None:
        self.gateway = gateway
        self.feature_registry = feature_registry

    def _request(
        self,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> ModelRequest:
        return to_model_request(
            spec,
            shot,
            feature_registry=self.feature_registry,
            excluded_provider_keys=excluded_provider_keys,
        )

    async def estimate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayEstimate:
        request = self._request(spec, shot, excluded_provider_keys)
        decision = self.gateway.router.route(request)
        if not decision.candidates:
            raise ValueError("VIDEO_NO_ROUTE_AVAILABLE")
        candidate = decision.candidates[0]
        if candidate.estimate.amount_usd is None:
            raise ValueError("VIDEO_PROVIDER_COST_ESTIMATE_REQUIRED")
        reasons = candidate.reason_codes
        if self.feature_registry is not None:
            reasons += (f"VIDEO_FEATURE_REGISTRY:{self.feature_registry.snapshot_id}",)
        return GatewayEstimate(
            amount_usd=candidate.estimate.amount_usd,
            provider=candidate.model.provider,
            model=candidate.model.model,
            pricing_snapshot_id=candidate.estimate.pricing_snapshot_id,
            routing_reason_codes=reasons,
        )

    async def submit(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayVideoResult:
        request = self._request(spec, shot, excluded_provider_keys)
        decision = self.gateway.router.route(request)
        result = await self.gateway.invoke(request)
        if result.status is not ResultStatus.PENDING:
            raise ValueError("VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED")
        if not result.provider_request_id:
            raise ValueError("VIDEO_PROVIDER_JOB_ID_REQUIRED")
        matching = next(
            (
                (index, candidate)
                for index, candidate in enumerate(decision.candidates)
                if candidate.model.provider == result.provider
                and candidate.model.model == result.model
            ),
            None,
        )
        reasons = ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        if matching is not None:
            index, candidate = matching
            reasons = candidate.reason_codes
            if index:
                reasons += (f"FALLBACK_INDEX:{index}",)
        return _normalize(result, reasons)

    async def poll(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        request_id = pending.result.provider_request_id
        if not request_id:
            raise ValueError("VIDEO_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        capability = Capability(pending.capability)
        result = await self.gateway.get_async_status(
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=request_id,
            capability=capability,
            queue_started_epoch=pending.queued_at_epoch,
        )
        if result.provider != pending.result.provider or result.model != pending.result.model:
            raise ValueError("VIDEO_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return _normalize(result, pending.result.routing_reason_codes)

    async def cancel(self, *, pending: ProviderJobRecord) -> bool:
        request_id = pending.result.provider_request_id
        if not request_id:
            return False
        return await self.gateway.cancel(
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=request_id,
        )


def pending_record(shot: CompiledShot, result: GatewayVideoResult) -> ProviderJobRecord:
    return ProviderJobRecord(
        shot_id=shot.shot.shot_id,
        operation_id=shot.paid_operation_id,
        capability=_capability(shot).value,
        queued_at_epoch=time.time(),
        result=result,
    )
