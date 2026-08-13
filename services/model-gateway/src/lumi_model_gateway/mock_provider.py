from __future__ import annotations

import asyncio
import json
from collections import deque
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
from .models import (
    Capability,
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelRequest,
    ModelResult,
    ProviderLatencyClass,
    ProviderModel,
    ResultStatus,
    StreamChunk,
    Timing,
    Usage,
)
from .pricing import PriceCard


@dataclass(frozen=True, slots=True)
class MockFailure:
    category: ErrorCategory
    delivery_state: DeliveryState = DeliveryState.NOT_ACCEPTED
    retry_after_seconds: float | None = None


class MockProvider:
    def __init__(
        self,
        *,
        provider: str = "mock",
        model: str = "mock-v1",
        quality_score: int = 80,
        failures: tuple[MockFailure, ...] = (),
    ) -> None:
        self._descriptor = ProviderModel(
            provider=provider,
            model=model,
            capabilities=frozenset(Capability),
            quality_score=quality_score,
            latency_class=ProviderLatencyClass.FAST,
            supports_streaming=True,
            supports_async=True,
        )
        self._failures = deque(failures)
        self._jobs: dict[str, tuple[ModelRequest, int, bool]] = {}
        self._price_card = PriceCard(
            snapshot_id="mock-price-v1",
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            image_usd_per_generation=Decimal("0.01"),
            video_usd_per_second=Decimal("0.002"),
            embedding_usd_per_million_tokens=Decimal("0.1"),
        )

    @property
    def descriptor(self) -> ProviderModel:
        return self._descriptor

    def validate(self, request: ModelRequest) -> None:
        if request.capability not in self._descriptor.capabilities:
            raise ProviderValidationError(
                ErrorCategory.INVALID_REQUEST,
                "mock capability unsupported",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate:
        self.validate(request)
        return self._price_card.estimate(request)

    async def invoke(self, request: ModelRequest) -> ModelResult:
        self.validate(request)
        self._raise_planned_failure()
        digest = request.semantic_hash[:24]
        if request.capability in {
            Capability.VIDEO_TEXT_TO_VIDEO,
            Capability.VIDEO_IMAGE_TO_VIDEO,
            Capability.VIDEO_EDIT,
        }:
            provider_request_id = f"mock-video-{digest}"
            self._jobs[provider_request_id] = (request, 0, False)
            estimate = await self.estimate_cost(request)
            return ModelResult(
                status=ResultStatus.PENDING,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                provider_request_id=provider_request_id,
                outputs=(),
                usage=Usage(),
                timing=Timing(total_ms=1),
                cost=estimate,
                finish_reason="queued",
            )
        return self._completed_result(request, digest=digest)

    async def get_async_status(self, provider_request_id: str) -> ModelResult:
        try:
            request, polls, cancelled = self._jobs[provider_request_id]
        except KeyError as exc:
            raise ProviderInvocationError(
                ErrorCategory.INVALID_REQUEST,
                "mock async job not found",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            ) from exc
        if cancelled:
            return ModelResult(
                status=ResultStatus.CANCELLED,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                provider_request_id=provider_request_id,
                outputs=(),
                usage=Usage(),
                timing=Timing(total_ms=1),
                cost=await self.estimate_cost(request),
                finish_reason="cancelled",
            )
        polls += 1
        self._jobs[provider_request_id] = (request, polls, False)
        if polls == 1:
            return ModelResult(
                status=ResultStatus.PENDING,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                provider_request_id=provider_request_id,
                outputs=(),
                usage=Usage(),
                timing=Timing(total_ms=1),
                cost=await self.estimate_cost(request),
                finish_reason="in_progress",
            )
        digest = request.semantic_hash[:24]
        result = self._completed_result(request, digest=digest)
        return ModelResult(
            status=result.status,
            provider=result.provider,
            model=result.model,
            provider_request_id=provider_request_id,
            outputs=result.outputs,
            usage=result.usage,
            timing=result.timing,
            cost=result.cost,
            finish_reason="completed",
        )

    async def cancel(self, provider_request_id: str) -> ModelResult:
        try:
            request, polls, _ = self._jobs[provider_request_id]
        except KeyError as exc:
            raise ProviderInvocationError(
                ErrorCategory.INVALID_REQUEST,
                "mock async job not found",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            ) from exc
        self._jobs[provider_request_id] = (request, polls, True)
        return await self.get_async_status(provider_request_id)

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        self.validate(request)
        self._raise_planned_failure()
        if request.capability not in {
            Capability.LLM_REASONING,
            Capability.LLM_STRUCTURED_OUTPUT,
        }:
            raise ProviderInvocationError(
                ErrorCategory.INVALID_REQUEST,
                "mock stream only supports LLM capabilities",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        result = self._completed_result(request, digest=request.semantic_hash[:24])
        if not result.outputs:
            return
        value = result.outputs[0].value
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        tokens = text.split(" ")
        for sequence, token in enumerate(tokens, start=1):
            await asyncio.sleep(0)
            suffix = " " if sequence < len(tokens) else ""
            yield StreamChunk(
                request_id=request.request_id,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                sequence=sequence,
                kind="text_delta",
                delta=token + suffix,
            )
        yield StreamChunk(
            request_id=request.request_id,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            sequence=len(tokens) + 1,
            kind="completed",
            usage=result.usage,
            finish_reason="completed",
        )

    def normalize_error(self, error: Exception) -> ProviderInvocationError:
        if isinstance(error, ProviderInvocationError):
            return error
        return ProviderInvocationError(
            ErrorCategory.UNKNOWN,
            str(error),
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.UNKNOWN,
        )

    def _raise_planned_failure(self) -> None:
        if not self._failures:
            return
        failure = self._failures.popleft()
        raise ProviderInvocationError(
            failure.category,
            f"mock planned failure: {failure.category.value}",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=failure.delivery_state,
            retry_after_seconds=failure.retry_after_seconds,
        )

    def _completed_result(self, request: ModelRequest, *, digest: str) -> ModelResult:
        if request.capability == Capability.LLM_STRUCTURED_OUTPUT:
            schema = request.structured_output_schema or {"type": "object"}
            value = _materialize_schema(schema, digest=digest)
            outputs = (
                ModelOutput(
                    kind="json",
                    value=value,
                    mime_type="application/json",
                ),
            )
            usage = Usage(input_tokens=32, output_tokens=24, total_tokens=56)
        elif request.capability in {
            Capability.LLM_REASONING,
            Capability.LLM_VISION,
            Capability.OCR_DOCUMENT,
        }:
            text = f"mock:{request.capability.value}:{digest}"
            outputs = (
                ModelOutput(kind="text", value=text, mime_type="text/plain"),
            )
            usage = Usage(input_tokens=32, output_tokens=16, total_tokens=48)
        elif request.capability in {
            Capability.IMAGE_GENERATE,
            Capability.IMAGE_EDIT,
            Capability.IMAGE_MASK_EDIT,
            Capability.IMAGE_REFERENCE_CONSISTENCY,
            Capability.IMAGE_TRANSPARENT_BACKGROUND,
        }:
            outputs = (
                ModelOutput(
                    kind="asset_ref",
                    value=f"fixture://mock/image/{digest}.png",
                    mime_type="image/png",
                ),
            )
            usage = Usage(
                image_output_tokens=1,
                units={"generations": Decimal("1")},
            )
        elif request.capability in {
            Capability.VIDEO_TEXT_TO_VIDEO,
            Capability.VIDEO_IMAGE_TO_VIDEO,
            Capability.VIDEO_EDIT,
        }:
            outputs = (
                ModelOutput(
                    kind="asset_ref",
                    value=f"fixture://mock/video/{digest}.mp4",
                    mime_type="video/mp4",
                ),
            )
            seconds = Decimal(str(request.constraints.get("duration_seconds", 5)))
            usage = Usage(seconds=seconds)
        else:
            vector = [
                round(int(digest[index : index + 2], 16) / 255, 6)
                for index in range(0, 16, 2)
            ]
            outputs = (ModelOutput(kind="embedding", value=vector),)
            usage = Usage(input_tokens=16, total_tokens=16)
        estimate = self._price_card.estimate(request)
        cost = CostEstimate(
            amount_usd=estimate.amount_usd,
            confidence=(
                CostConfidence.EXACT
                if estimate.amount_usd is not None
                else CostConfidence.UNKNOWN
            ),
            price_snapshot_id=estimate.price_snapshot_id,
            detail=estimate.detail,
        )
        return ModelResult(
            status=ResultStatus.SUCCEEDED,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            provider_request_id=f"mock-{digest}",
            outputs=outputs,
            usage=usage,
            timing=Timing(total_ms=1, ttft_ms=1),
            cost=cost,
            safety_metadata={"mock": True},
            finish_reason="completed",
        )


def _materialize_schema(schema: dict[str, Any], *, digest: str) -> Any:
    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return {}
        return {
            str(name): _materialize_schema(value, digest=digest)
            for name, value in sorted(properties.items())
            if isinstance(value, dict)
        }
    if schema_type == "array":
        items = schema.get("items", {"type": "string"})
        if isinstance(items, dict):
            return [_materialize_schema(items, digest=digest)]
        return []
    if schema_type == "integer":
        return int(digest[:4], 16)
    if schema_type == "number":
        return round(int(digest[:4], 16) / 1000, 3)
    if schema_type == "boolean":
        return int(digest[0], 16) % 2 == 0
    return f"mock-{digest[:12]}"
