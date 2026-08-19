from __future__ import annotations

import asyncio
import base64
import binascii
import json
import socket
import urllib.error
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .errors import (
    DeliveryState,
    ErrorCategory,
    ProviderInvocationError,
    ProviderValidationError,
)
from .media_output import ProviderBinaryOutputStore
from .models import (
    Capability,
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelRequest,
    ModelResult,
    ProviderLatencyClass,
    ProviderModel,
    QualityProfile,
    ResultStatus,
    StreamChunk,
    Timing,
    Usage,
)
from .openai_adapter import HttpResponse, HttpTransport, UrllibHttpTransport

_OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_MAX_B64_CHARS = ((_MAX_IMAGE_BYTES + 2) // 3) * 4 + 16
_SUPPORTED_SIZES = frozenset({"1024x1024", "1024x1536", "1536x1024"})
_FORMATS = {
    "png": ("image/png", "png"),
    "jpeg": ("image/jpeg", "jpeg"),
    "webp": ("image/webp", "webp"),
}
_QUALITY = {
    QualityProfile.DRAFT: "low",
    QualityProfile.BALANCED: "medium",
    QualityProfile.HIGH: "high",
    QualityProfile.MAX: "high",
}


@dataclass(frozen=True, slots=True)
class OpenAIImagePriceCard:
    snapshot_id: str
    max_estimated_request_usd: Decimal
    text_input_usd_per_million_tokens: Decimal
    image_input_usd_per_million_tokens: Decimal
    image_output_usd_per_million_tokens: Decimal

    def __post_init__(self) -> None:
        if not self.snapshot_id or len(self.snapshot_id) > 128:
            raise ValueError("OPENAI_IMAGE_PRICE_SNAPSHOT_INVALID")
        for value in (
            self.max_estimated_request_usd,
            self.text_input_usd_per_million_tokens,
            self.image_input_usd_per_million_tokens,
            self.image_output_usd_per_million_tokens,
        ):
            if not value.is_finite() or value < 0:
                raise ValueError("OPENAI_IMAGE_PRICE_INVALID")
        if self.max_estimated_request_usd <= 0:
            raise ValueError("OPENAI_IMAGE_MAX_ESTIMATE_REQUIRED")

    def estimate(self, *, size: str, quality: str) -> CostEstimate:
        return CostEstimate(
            amount_usd=self.max_estimated_request_usd,
            confidence=CostConfidence.ESTIMATED,
            price_snapshot_id=self.snapshot_id,
            detail={
                "basis": "configured_request_ceiling",
                "size": size,
                "quality": quality,
            },
        )

    def actual(self, usage: Usage) -> CostEstimate:
        text_tokens = usage.units.get("text_input_tokens", Decimal(0))
        image_input_tokens = usage.units.get("image_input_tokens", Decimal(0))
        image_output_tokens = usage.units.get("image_output_tokens", Decimal(0))
        amount = (
            text_tokens * self.text_input_usd_per_million_tokens
            + image_input_tokens * self.image_input_usd_per_million_tokens
            + image_output_tokens * self.image_output_usd_per_million_tokens
        ) / Decimal(1_000_000)
        return CostEstimate(
            amount_usd=amount,
            confidence=CostConfidence.EXACT,
            price_snapshot_id=self.snapshot_id,
            detail={
                "text_input_tokens": int(text_tokens),
                "image_input_tokens": int(image_input_tokens),
                "image_output_tokens": int(image_output_tokens),
            },
        )


class OpenAIImageGenerationAdapter:
    """Hosted OpenAI image generation adapter with bounded binary staging.

    The provider's base64 image never becomes a ModelResult JSON value. It is
    decoded under a hard byte ceiling, staged through ProviderBinaryOutputStore,
    and only an opaque asset reference crosses back through Model Gateway.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        price_card: OpenAIImagePriceCard,
        output_store: ProviderBinaryOutputStore,
        transport: HttpTransport | None = None,
        organization: str | None = None,
        project: str | None = None,
        timeout_seconds: float = 180.0,
        quality_score: int = 92,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_IMAGE_API_KEY_REQUIRED")
        if not model:
            raise ValueError("OPENAI_IMAGE_MODEL_REQUIRED")
        if not 1 <= timeout_seconds <= 600:
            raise ValueError("OPENAI_IMAGE_TIMEOUT_INVALID")
        self._api_key = api_key
        self._organization = organization
        self._project = project
        self._price_card = price_card
        self._output_store = output_store
        self._transport = transport or UrllibHttpTransport()
        self._timeout_seconds = timeout_seconds
        self._descriptor = ProviderModel(
            provider="openai",
            model=model,
            capabilities=frozenset(
                {
                    Capability.IMAGE_GENERATE,
                    Capability.IMAGE_TRANSPARENT_BACKGROUND,
                }
            ),
            quality_score=quality_score,
            latency_class=ProviderLatencyClass.SLOW,
            supports_streaming=False,
            supports_async=False,
        )

    @property
    def descriptor(self) -> ProviderModel:
        return self._descriptor

    def __repr__(self) -> str:
        return f"OpenAIImageGenerationAdapter(model={self._descriptor.model!r})"

    def validate(self, request: ModelRequest) -> None:
        if request.capability not in self._descriptor.capabilities:
            raise self._validation("image adapter does not expose this capability")
        if request.reference_assets:
            raise self._validation("reference assets require an image-edit adapter")
        self._prompt(request)
        size = self._size(request)
        if size not in _SUPPORTED_SIZES:
            raise self._validation(
                "exact target size is unsupported by the hosted image provider",
                category=ErrorCategory.HARD_CONSTRAINT_INVALID,
            )
        output_format = self._output_format(request)
        transparent = self._transparent(request)
        if transparent and output_format != "png":
            raise self._validation(
                "transparent image generation requires PNG output",
                category=ErrorCategory.HARD_CONSTRAINT_INVALID,
            )
        seed = request.inputs.get("seed")
        if seed is not None:
            raise self._validation(
                "deterministic seed is not supported by this hosted image adapter",
                category=ErrorCategory.HARD_CONSTRAINT_INVALID,
            )

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate:
        self.validate(request)
        return self._price_card.estimate(
            size=self._size(request),
            quality=_QUALITY[request.quality_profile],
        )

    async def invoke(self, request: ModelRequest) -> ModelResult:
        self.validate(request)
        output_format = self._output_format(request)
        mime_type, extension = _FORMATS[output_format]
        payload: dict[str, Any] = {
            "model": self._descriptor.model,
            "prompt": self._prompt(request),
            "n": 1,
            "size": self._size(request),
            "quality": _QUALITY[request.quality_profile],
            "output_format": output_format,
        }
        if self._transparent(request):
            payload["background"] = "transparent"
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        headers = {
            "authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }
        if self._organization:
            headers["openai-organization"] = self._organization
        if self._project:
            headers["openai-project"] = self._project
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            response = await asyncio.to_thread(
                self._transport.request,
                method="POST",
                url=_OPENAI_IMAGES_URL,
                headers=headers,
                body=encoded,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        elapsed_ms = int((loop.time() - started) * 1000)
        if not 200 <= response.status < 300:
            raise self._http_error(response)
        provider_request_id = response.headers.get("x-request-id")
        if not provider_request_id:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "successful image response did not include x-request-id",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.ACCEPTED,
            )
        raw_image, usage = self._parse_response(response.body)
        asset_ref = await self._output_store.store_bytes(
            request=request,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            data=raw_image,
            content_type=mime_type,
            extension=extension,
        )
        return ModelResult(
            status=ResultStatus.SUCCEEDED,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            provider_request_id=provider_request_id,
            outputs=(ModelOutput(kind="asset_ref", value=asset_ref, mime_type=mime_type),),
            usage=usage,
            timing=Timing(total_ms=elapsed_ms),
            cost=self._price_card.actual(usage),
            safety_metadata={},
            finish_reason="completed",
            raw_response_ref=None,
        )

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        async def unsupported() -> AsyncIterator[StreamChunk]:
            del request
            raise ProviderInvocationError(
                ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
                "hosted image streaming is not enabled",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
            yield  # pragma: no cover

        return unsupported()

    async def get_async_status(self, provider_request_id: str) -> ModelResult:
        del provider_request_id
        raise ProviderInvocationError(
            ErrorCategory.INVALID_REQUEST,
            "image generation adapter is synchronous",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    async def cancel(self, provider_request_id: str) -> ModelResult:
        del provider_request_id
        raise ProviderInvocationError(
            ErrorCategory.INVALID_REQUEST,
            "image generation adapter has no cancellable background job",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    def normalize_error(self, error: Exception) -> ProviderInvocationError:
        if isinstance(error, ProviderInvocationError):
            return error
        if isinstance(error, (TimeoutError, socket.timeout, urllib.error.URLError)):
            category = (
                ErrorCategory.TIMEOUT
                if isinstance(error, (TimeoutError, socket.timeout))
                else ErrorCategory.PROVIDER_UNAVAILABLE
            )
            return ProviderInvocationError(
                category,
                "OpenAI image network outcome is unknown",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.UNKNOWN,
            )
        return ProviderInvocationError(
            ErrorCategory.UNKNOWN,
            type(error).__name__,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.UNKNOWN,
        )

    def _prompt(self, request: ModelRequest) -> str:
        prompt = request.inputs.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            if len(prompt) > 64_000:
                raise self._validation("image prompt is too long")
            return prompt.strip()
        blocks = request.inputs.get("prompt_blocks")
        if not isinstance(blocks, dict):
            raise self._validation("image request requires prompt or prompt_blocks")
        sections: list[str] = []
        scalar_fields = (
            ("objective", "Objective"),
            ("content", "Content"),
            ("visual_direction", "Visual direction"),
            ("output_dimensions", "Output dimensions"),
        )
        for key, label in scalar_fields:
            value = blocks.get(key)
            if isinstance(value, str) and value.strip():
                sections.append(f"{label}: {value.strip()}")
        for key, label in (
            ("brand_constraints", "Brand constraints"),
            ("identity_requirements", "Identity requirements"),
            ("negative_constraints", "Negative constraints"),
        ):
            raw = blocks.get(key, [])
            if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
                raise self._validation(f"invalid {key}")
            values = [item.strip() for item in raw if item.strip()]
            if values:
                sections.append(f"{label}: " + "; ".join(values))
        compiled = "\n".join(sections)
        if not compiled or len(compiled) > 64_000:
            raise self._validation("compiled image prompt is empty or too long")
        return compiled

    def _size(self, request: ModelRequest) -> str:
        width = request.constraints.get("target_width", request.inputs.get("width"))
        height = request.constraints.get("target_height", request.inputs.get("height"))
        if (
            isinstance(width, bool)
            or isinstance(height, bool)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or width <= 0
            or height <= 0
        ):
            raise self._validation("image target dimensions are required")
        input_width = request.inputs.get("width")
        input_height = request.inputs.get("height")
        if input_width is not None and input_width != width:
            raise self._validation("image width conflicts with hard constraints")
        if input_height is not None and input_height != height:
            raise self._validation("image height conflicts with hard constraints")
        return f"{width}x{height}"

    def _output_format(self, request: ModelRequest) -> str:
        value = request.constraints.get("output_format", request.inputs.get("format", "png"))
        if not isinstance(value, str):
            raise self._validation("image output format is invalid")
        normalized = value.strip().lower()
        if normalized == "jpg":
            normalized = "jpeg"
        if normalized not in _FORMATS:
            raise self._validation("image output format is unsupported")
        input_format = request.inputs.get("format")
        if isinstance(input_format, str):
            normalized_input = input_format.strip().lower().replace("jpg", "jpeg")
            if normalized_input != normalized:
                raise self._validation("image output format conflicts with hard constraints")
        return normalized

    def _transparent(self, request: ModelRequest) -> bool:
        value = request.constraints.get(
            "transparent_background",
            request.inputs.get("transparent_background", False),
        )
        if not isinstance(value, bool):
            raise self._validation("transparent_background must be boolean")
        input_value = request.inputs.get("transparent_background")
        if input_value is not None and input_value != value:
            raise self._validation("transparent background conflicts with hard constraints")
        if request.capability == Capability.IMAGE_TRANSPARENT_BACKGROUND and not value:
            raise self._validation("transparent capability requires transparent_background=true")
        return value

    def _parse_response(self, body: bytes) -> tuple[bytes, Usage]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise self._accepted_error("image provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise self._accepted_error("image provider returned invalid response object")
        b64_value: Any = payload.get("b64_json")
        if b64_value is None:
            data = payload.get("data")
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                b64_value = data[0].get("b64_json")
        if not isinstance(b64_value, str) or not b64_value:
            raise self._accepted_error("image provider response is missing b64_json")
        if len(b64_value) > _MAX_B64_CHARS:
            raise self._accepted_error("image provider output exceeds encoded size limit")
        try:
            raw = base64.b64decode(b64_value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise self._accepted_error("image provider returned invalid base64") from exc
        if not raw or len(raw) > _MAX_IMAGE_BYTES:
            raise self._accepted_error("image provider output exceeds raw size limit")
        usage_payload = payload.get("usage")
        if not isinstance(usage_payload, dict):
            raise self._accepted_error("GPT image response is missing token usage")
        return raw, _usage(usage_payload)

    def _http_error(self, response: HttpResponse) -> ProviderInvocationError:
        category = ErrorCategory.UNKNOWN
        delivery = DeliveryState.UNKNOWN
        if response.status in {401, 403}:
            category = ErrorCategory.AUTH_ERROR
            delivery = DeliveryState.NOT_ACCEPTED
        elif response.status == 429:
            category = ErrorCategory.RATE_LIMIT
            delivery = DeliveryState.NOT_ACCEPTED
        elif response.status in {400, 404, 409, 422}:
            category = ErrorCategory.INVALID_REQUEST
            delivery = DeliveryState.NOT_ACCEPTED
        elif response.status == 408:
            category = ErrorCategory.TIMEOUT
        elif 500 <= response.status <= 599:
            category = ErrorCategory.PROVIDER_5XX
        message, provider_code = _extract_error(response.body)
        return ProviderInvocationError(
            category,
            message or f"OpenAI image HTTP {response.status}",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=delivery,
            provider_code=provider_code,
        )

    def _validation(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.INVALID_REQUEST,
    ) -> ProviderValidationError:
        return ProviderValidationError(
            category,
            message,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    def _accepted_error(self, message: str) -> ProviderInvocationError:
        return ProviderInvocationError(
            ErrorCategory.UNKNOWN,
            message,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.ACCEPTED,
        )


def _usage(payload: dict[str, Any]) -> Usage:
    input_tokens = _nonnegative_int(payload.get("input_tokens"), "input_tokens")
    output_tokens = _nonnegative_int(payload.get("output_tokens"), "output_tokens")
    total_tokens = _nonnegative_int(payload.get("total_tokens"), "total_tokens")
    details = payload.get("input_tokens_details")
    if not isinstance(details, dict):
        raise ValueError("OPENAI_IMAGE_USAGE_DETAILS_INVALID")
    text_tokens = _nonnegative_int(details.get("text_tokens"), "text_tokens")
    image_tokens = _nonnegative_int(details.get("image_tokens"), "image_tokens")
    if total_tokens != input_tokens + output_tokens:
        raise ValueError("OPENAI_IMAGE_USAGE_TOTAL_MISMATCH")
    if input_tokens != text_tokens + image_tokens:
        raise ValueError("OPENAI_IMAGE_USAGE_INPUT_MISMATCH")
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        image_input_tokens=image_tokens,
        image_output_tokens=output_tokens,
        units={
            "text_input_tokens": Decimal(text_tokens),
            "image_input_tokens": Decimal(image_tokens),
            "image_output_tokens": Decimal(output_tokens),
        },
    )


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"OPENAI_IMAGE_USAGE_{name.upper()}_INVALID")
    return value


def _extract_error(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None, None
    error = payload["error"]
    message = error.get("message")
    code = error.get("code")
    return (
        str(message) if message is not None else None,
        str(code) if code is not None else None,
    )
