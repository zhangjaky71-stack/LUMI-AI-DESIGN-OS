from __future__ import annotations

import os
from dataclasses import replace

from lumi_model_gateway import HttpModelGatewayAsyncClient, ResultStatus
from lumi_model_gateway.models import ModelRequest, ModelResult
from lumi_video_generation.model import (
    CompiledShot,
    GatewayEstimate,
    GatewayVideoResult,
    ProviderJobRecord,
    VideoTaskSpec,
)
from lumi_video_generation.model_gateway_adapter import to_model_request


class HostedVideoGateway:
    """Worker-side NODE-48 gateway over the private signed Model Gateway only."""

    def __init__(self, *, client: HttpModelGatewayAsyncClient, model_profile: str) -> None:
        if (
            not model_profile
            or len(model_profile) > 100
            or model_profile != model_profile.strip()
            or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.+-" for char in model_profile)
        ):
            raise ValueError("VIDEO_MODEL_PROFILE_INVALID")
        self.client = client
        self.model_profile = model_profile

    @classmethod
    def from_env(cls) -> HostedVideoGateway:
        base_url = os.getenv("LUMI_MODEL_GATEWAY_URL", "")
        auth_secret = os.getenv("LUMI_MODEL_GATEWAY_AUTH_SECRET", "")
        profile = os.getenv("LUMI_VIDEO_MODEL_PROFILE", "")
        if not base_url:
            raise RuntimeError("LUMI_MODEL_GATEWAY_URL_REQUIRED")
        if not auth_secret:
            raise RuntimeError("LUMI_MODEL_GATEWAY_AUTH_SECRET_REQUIRED")
        if not profile:
            raise RuntimeError("LUMI_VIDEO_MODEL_PROFILE_REQUIRED")
        return cls(
            client=HttpModelGatewayAsyncClient(
                base_url=base_url,
                auth_secret=auth_secret,
                caller_service="worker-media",
                timeout_seconds=180.0,
            ),
            model_profile=profile,
        )

    async def estimate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        continuity_refs: tuple[str, ...],
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayEstimate:
        request = self._request(spec, shot, continuity_refs, excluded_provider_keys)
        estimate = await self.client.estimate(request)
        if estimate.amount_usd is None:
            raise RuntimeError("VIDEO_PROVIDER_COST_ESTIMATE_REQUIRED")
        return GatewayEstimate(
            amount_usd=estimate.amount_usd,
            provider=estimate.provider,
            model=estimate.model,
            pricing_snapshot_id=estimate.price_snapshot_id,
            routing_reason_codes=tuple(estimate.reason_codes)
            + (f"MODEL_PROFILE:{self.model_profile}",),
        )

    async def submit(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        continuity_refs: tuple[str, ...],
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayVideoResult:
        request = self._request(spec, shot, continuity_refs, excluded_provider_keys)
        route = await self.client.estimate(request)
        result = await self.client.invoke(request)
        if result.status != ResultStatus.PENDING:
            raise RuntimeError("VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED")
        if not result.provider_request_id:
            raise RuntimeError("VIDEO_PROVIDER_JOB_ID_REQUIRED")
        reasons = tuple(route.reason_codes) + (f"MODEL_PROFILE:{self.model_profile}",)
        if result.provider != route.provider or result.model != route.model:
            reasons += ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        if excluded_provider_keys:
            reasons += (f"VIDEO_EXCLUDED_PROVIDERS:{len(set(excluded_provider_keys))}",)
        return _normalize(result, reasons)

    async def poll(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        request_id = pending.result.provider_request_id
        if not request_id:
            raise RuntimeError("VIDEO_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        result = await self.client.get_async_status(
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=request_id,
        )
        if result.provider != pending.result.provider or result.model != pending.result.model:
            raise RuntimeError("VIDEO_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return _normalize(result, pending.result.routing_reason_codes)

    async def cancel(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        request_id = pending.result.provider_request_id
        if not request_id:
            raise RuntimeError("VIDEO_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        result = await self.client.cancel(
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=request_id,
        )
        if result.provider != pending.result.provider or result.model != pending.result.model:
            raise RuntimeError("VIDEO_ASYNC_PROVIDER_IDENTITY_CHANGED")
        return _normalize(result, pending.result.routing_reason_codes)

    def _request(
        self,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        continuity_refs: tuple[str, ...],
        excluded_provider_keys: tuple[str, ...],
    ) -> ModelRequest:
        if spec.mode != "TEXT_TO_VIDEO" or spec.source_images:
            raise ValueError("VIDEO_HOSTED_V1_TEXT_TO_VIDEO_ONLY")
        if continuity_refs or shot.shot.source_ref is not None:
            raise ValueError("VIDEO_HOSTED_V1_REFERENCE_INPUT_UNSUPPORTED")
        if spec.negative_prompt is not None:
            raise ValueError("VIDEO_HOSTED_V1_NEGATIVE_PROMPT_UNSUPPORTED")
        if spec.seed is not None:
            raise ValueError("VIDEO_HOSTED_V1_SEED_UNSUPPORTED")
        if shot.shot.camera_motion is not None:
            raise ValueError("VIDEO_HOSTED_V1_CAMERA_MOTION_UNSUPPORTED")
        if shot.shot.subject_action is not None:
            raise ValueError("VIDEO_HOSTED_V1_SUBJECT_ACTION_UNSUPPORTED")
        request = to_model_request(
            spec,
            shot,
            continuity_refs,
            feature_registry=None,
            excluded_provider_keys=excluded_provider_keys,
        )
        constraints = dict(request.constraints)
        constraints["model_profile"] = self.model_profile
        return replace(request, constraints=constraints)


def _normalize(
    result: ModelResult,
    routing_reason_codes: tuple[str, ...],
) -> GatewayVideoResult:
    output_ref: str | None = None
    output_mime: str | None = None
    if result.status == ResultStatus.SUCCEEDED:
        if len(result.outputs) != 1:
            raise RuntimeError("VIDEO_GATEWAY_OUTPUT_COUNT_INVALID")
        output = result.outputs[0]
        if output.kind != "asset_ref" or not isinstance(output.value, str):
            raise RuntimeError("VIDEO_GATEWAY_OUTPUT_MUST_BE_ASSET_REF")
        if output.mime_type != "video/mp4":
            raise RuntimeError("VIDEO_GATEWAY_OUTPUT_MIME_INVALID")
        output_ref = output.value
        output_mime = output.mime_type
    return GatewayVideoResult(
        status=result.status.value.upper(),  # type: ignore[arg-type]
        provider=result.provider,
        model=result.model,
        provider_request_id=result.provider_request_id,
        output_ref=output_ref,
        output_mime_type=output_mime,
        cost_usd=result.cost.amount_usd,
        cost_confidence=result.cost.confidence.value.upper(),
        pricing_snapshot_id=result.cost.price_snapshot_id,
        routing_reason_codes=routing_reason_codes,
        safety_metadata=result.safety_metadata,
        finish_reason=result.finish_reason,
    )
