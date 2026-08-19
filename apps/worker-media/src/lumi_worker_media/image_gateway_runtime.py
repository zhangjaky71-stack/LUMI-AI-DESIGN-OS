from __future__ import annotations

import os
from typing import cast
from urllib.parse import urlsplit

from lumi_asset_storage.s3 import S3ObjectStore
from lumi_image_generation.model import (
    FetchedImage,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GatewayResultStatus,
    ProviderOutputRef,
)
from lumi_image_generation.model_gateway_adapter import to_model_request
from lumi_image_generation.ports import GatewayEstimate
from lumi_model_gateway.estimate_transport import HttpModelGatewayEstimateClient
from lumi_model_gateway.models import ModelResult

_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_PROVIDER_OUTPUT_PREFIX = "provider-output/v1/"


class HostedImageModelGatewayAdapter:
    """NODE-46 image gateway port backed only by the private NODE-22 HTTP service."""

    def __init__(self, client: HttpModelGatewayEstimateClient) -> None:
        self.client = client

    @classmethod
    def from_env(cls) -> HostedImageModelGatewayAdapter:
        base_url = _required_env("LUMI_MODEL_GATEWAY_URL", max_length=2048)
        auth_secret = _required_env("LUMI_MODEL_GATEWAY_AUTH_SECRET", max_length=8192)
        return cls(
            HttpModelGatewayEstimateClient(
                base_url=base_url,
                auth_secret=auth_secret,
                caller_service="worker-media",
                timeout_seconds=120.0,
            )
        )

    async def estimate(self, request: GatewayGenerationRequest) -> GatewayEstimate:
        estimate = await self.client.estimate(to_model_request(request))
        if estimate.amount_usd is None:
            raise ValueError("GENERATION_PROVIDER_COST_ESTIMATE_REQUIRED")
        return GatewayEstimate(
            amount_usd=estimate.amount_usd,
            pricing_snapshot_id=estimate.price_snapshot_id,
            provider=estimate.provider,
            model=estimate.model,
            routing_reason_codes=estimate.reason_codes,
        )

    async def invoke(self, request: GatewayGenerationRequest) -> GatewayGenerationResult:
        model_request = to_model_request(request)
        routed = await self.client.estimate(model_request)
        result = await self.client.invoke(model_request)
        reasons = (
            routed.reason_codes
            if routed.provider == result.provider and routed.model == result.model
            else ("ROUTE_DECISION_CHANGED_DURING_INVOKE",)
        )
        return _generation_result(request, result, reasons)

    async def poll(
        self,
        *,
        request: GatewayGenerationRequest,
        pending_result: GatewayGenerationResult,
    ) -> GatewayGenerationResult:
        del request, pending_result
        # The currently hosted OpenAI image adapter is synchronous. Do not fake
        # async reconciliation support through another provider request.
        raise RuntimeError("HOSTED_IMAGE_PROVIDER_PENDING_UNSUPPORTED")


class S3ProviderOutputFetcher:
    """Reads only opaque image outputs staged by Model Gateway in the assets bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        object_store: S3ObjectStore,
        max_bytes: int = _MAX_IMAGE_BYTES,
    ) -> None:
        if not bucket or "/" in bucket or bucket != bucket.strip():
            raise ValueError("PROVIDER_OUTPUT_BUCKET_INVALID")
        if not 1 <= max_bytes <= _MAX_IMAGE_BYTES:
            raise ValueError("PROVIDER_OUTPUT_MAX_BYTES_INVALID")
        self.bucket = bucket
        self.object_store = object_store
        self.max_bytes = max_bytes

    @classmethod
    def from_env(cls) -> S3ProviderOutputFetcher:
        bucket = _required_env("LUMI_S3_BUCKET", max_length=255)
        region = os.getenv("LUMI_S3_REGION") or os.getenv("AWS_REGION") or "us-east-1"
        return cls(
            bucket=bucket,
            object_store=S3ObjectStore(
                endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL"),
                region_name=region,
                access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY"),
                force_path_style=_env_bool("LUMI_S3_FORCE_PATH_STYLE"),
            ),
        )

    async def fetch(self, ref: str, declared_mime_type: str | None) -> FetchedImage:
        object_key = _provider_output_key(ref, expected_bucket=self.bucket)
        content = await self.object_store.get_bytes(
            bucket=self.bucket,
            object_key=object_key,
            max_bytes=self.max_bytes,
        )
        return FetchedImage(
            source_ref=ref,
            content=content,
            declared_mime_type=declared_mime_type,
        )


def _generation_result(
    request: GatewayGenerationRequest,
    result: ModelResult,
    routing_reason_codes: tuple[str, ...],
) -> GatewayGenerationResult:
    outputs: list[ProviderOutputRef] = []
    for output in result.outputs:
        if output.kind != "asset_ref" or not isinstance(output.value, str):
            raise ValueError("IMAGE_GATEWAY_OUTPUT_MUST_BE_ASSET_REF")
        _provider_output_key(output.value, expected_bucket=None)
        outputs.append(ProviderOutputRef(ref=output.value, mime_type=output.mime_type))
    return GatewayGenerationResult(
        status=cast(GatewayResultStatus, result.status.value.upper()),
        provider=result.provider,
        model=result.model,
        model_revision=None,
        provider_request_id=result.provider_request_id,
        outputs=tuple(outputs),
        cost_usd=result.cost.amount_usd,
        cost_confidence=result.cost.confidence.value,
        pricing_snapshot_id=result.cost.price_snapshot_id,
        routing_reason_codes=routing_reason_codes,
        safety_metadata=result.safety_metadata,
        finish_reason=result.finish_reason,
        seed=request.seed,
    )


def _provider_output_key(ref: str, *, expected_bucket: str | None) -> str:
    if not isinstance(ref, str) or len(ref) > 2048:
        raise ValueError("PROVIDER_OUTPUT_REF_INVALID")
    parsed = urlsplit(ref)
    if (
        parsed.scheme != "s3"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PROVIDER_OUTPUT_REF_INVALID")
    if expected_bucket is not None and parsed.netloc != expected_bucket:
        raise ValueError("PROVIDER_OUTPUT_BUCKET_MISMATCH")
    if "%" in parsed.path or "\\" in parsed.path:
        raise ValueError("PROVIDER_OUTPUT_KEY_ENCODING_FORBIDDEN")
    object_key = parsed.path.lstrip("/")
    if not object_key.startswith(_PROVIDER_OUTPUT_PREFIX):
        raise ValueError("PROVIDER_OUTPUT_PREFIX_FORBIDDEN")
    segments = object_key.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("PROVIDER_OUTPUT_KEY_INVALID")
    return object_key


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _env_bool(name: str) -> bool:
    value = os.getenv(name, "").strip().casefold()
    if not value:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name}_INVALID")
