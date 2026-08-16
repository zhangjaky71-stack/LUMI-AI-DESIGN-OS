from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from .errors import ErrorCategory, ProviderAcceptance, ProviderCallError
from .models import (
    Capability,
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelRequest,
    ModelStreamChunk,
    ModelUsage,
    NormalizedResult,
    ProviderModel,
    ResultStatus,
    StreamEventType,
)


class MockProvider:
    provider_name = "mock"

    def __init__(self) -> None:
        self._jobs: dict[str, tuple[int, ProviderModel]] = {}
        all_llm = frozenset(
            {Capability.LLM_REASONING, Capability.LLM_STRUCTURED_OUTPUT, Capability.LLM_VISION}
        )
        self._models = (
            ProviderModel("mock", "mock-llm-v1", all_llm, 75, 95, paid=False, fixed_request_usd=Decimal("0.001")),
            ProviderModel(
                "mock",
                "mock-image-v1",
                frozenset(
                    {
                        Capability.IMAGE_GENERATE,
                        Capability.IMAGE_EDIT,
                        Capability.IMAGE_MASK_EDIT,
                        Capability.IMAGE_REFERENCE_CONSISTENCY,
                        Capability.IMAGE_TRANSPARENT_BACKGROUND,
                    }
                ),
                70,
                90,
                paid=False,
                fixed_request_usd=Decimal("0.01"),
            ),
            ProviderModel(
                "mock",
                "mock-video-v1",
                frozenset({Capability.VIDEO_TEXT_TO_VIDEO, Capability.VIDEO_IMAGE_TO_VIDEO}),
                65,
                50,
                paid=False,
                fixed_request_usd=Decimal("0.05"),
            ),
            ProviderModel(
                "mock",
                "mock-utility-v1",
                frozenset(
                    {
                        Capability.EMBEDDING_TEXT,
                        Capability.EMBEDDING_MULTIMODAL,
                        Capability.OCR_DOCUMENT,
                    }
                ),
                60,
                95,
                paid=False,
                fixed_request_usd=Decimal("0.0001"),
            ),
        )
        self.invocations = 0

    def models(self) -> tuple[ProviderModel, ...]:
        return self._models

    def validate(self, request: ModelRequest, model: ProviderModel) -> None:
        if request.capability not in model.capabilities:
            raise ValueError("mock model capability mismatch")

    def estimate_cost(self, request: ModelRequest, model: ProviderModel) -> CostEstimate:
        del request
        return CostEstimate(model.fixed_request_usd or Decimal("0"), CostConfidence.EXACT, "mock-v1")

    async def invoke(self, request: ModelRequest, model: ProviderModel) -> NormalizedResult:
        self.validate(request, model)
        self.invocations += 1
        simulated = request.constraints.get("simulate_error")
        if simulated:
            category = ErrorCategory(str(simulated))
            acceptance_value = request.constraints.get("simulate_acceptance") or "not_accepted"
            acceptance = ProviderAcceptance(str(acceptance_value))
            raise ProviderCallError(
                category,
                f"simulated {category.value}",
                provider=self.provider_name,
                status_code=429 if category is ErrorCategory.RATE_LIMIT else 503,
                retryable=category in {
                    ErrorCategory.RATE_LIMIT,
                    ErrorCategory.TIMEOUT,
                    ErrorCategory.PROVIDER_5XX,
                    ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
                },
                acceptance=acceptance,
            )
        digest = request.semantic_hash()[:20]
        estimate = self.estimate_cost(request, model)
        usage = ModelUsage(input_tokens=17, output_tokens=11)
        if request.capability in {
            Capability.VIDEO_TEXT_TO_VIDEO,
            Capability.VIDEO_IMAGE_TO_VIDEO,
        }:
            provider_request_id = f"mock-video-{digest}"
            self._jobs[provider_request_id] = (0, model)
            return NormalizedResult(
                ResultStatus.PENDING,
                self.provider_name,
                model.model,
                provider_request_id=provider_request_id,
                usage=usage,
                cost=estimate,
            )
        if request.capability.value.startswith("image."):
            output = ModelOutput(kind="asset", asset_ref=f"fixture://mock/image/{digest}.png")
        elif request.capability.value.startswith("embedding."):
            output = ModelOutput(kind="json", json_value={"embedding": [0.1, 0.2, 0.3], "digest": digest})
        elif request.capability is Capability.OCR_DOCUMENT:
            output = ModelOutput(kind="text", text=f"mock-ocr:{digest}")
        elif request.structured_output_schema:
            value = _synthesize(request.structured_output_schema)
            output = ModelOutput(kind="json", json_value=value, text=json.dumps(value, sort_keys=True))
        else:
            output = ModelOutput(kind="text", text=f"mock:{digest}")
        return NormalizedResult(
            ResultStatus.COMPLETED,
            self.provider_name,
            model.model,
            outputs=(output,),
            provider_request_id=f"mock-{digest}",
            usage=usage,
            finish_reason="stop",
            cost=estimate,
        )

    async def stream(self, request: ModelRequest, model: ProviderModel):
        self.validate(request, model)
        digest = request.semantic_hash()[:12]
        request_id = f"mock-stream-{digest}"
        yield ModelStreamChunk(StreamEventType.STARTED, self.provider_name, model.model, provider_request_id=request_id)
        for part in ("mock", ":", digest):
            yield ModelStreamChunk(StreamEventType.TEXT_DELTA, self.provider_name, model.model, text_delta=part, provider_request_id=request_id)
        usage = ModelUsage(input_tokens=7, output_tokens=5)
        yield ModelStreamChunk(StreamEventType.USAGE, self.provider_name, model.model, usage=usage, provider_request_id=request_id)
        yield ModelStreamChunk(StreamEventType.COMPLETED, self.provider_name, model.model, usage=usage, provider_request_id=request_id, finish_reason="stop")

    async def get_async_status(self, provider_request_id: str, model: ProviderModel) -> NormalizedResult:
        state = self._jobs.get(provider_request_id)
        if state is None:
            raise ProviderCallError(
                ErrorCategory.INVALID_REQUEST,
                "unknown mock job",
                provider=self.provider_name,
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
            )
        count, stored_model = state
        if stored_model.model != model.model:
            raise ProviderCallError(
                ErrorCategory.INVALID_REQUEST,
                "mock job model mismatch",
                provider=self.provider_name,
                acceptance=ProviderAcceptance.NOT_ACCEPTED,
            )
        self._jobs[provider_request_id] = (count + 1, stored_model)
        if count == 0:
            return NormalizedResult(
                ResultStatus.PENDING,
                self.provider_name,
                model.model,
                provider_request_id=provider_request_id,
                cost=CostEstimate(model.fixed_request_usd, CostConfidence.EXACT, "mock-v1"),
            )
        digest = provider_request_id.removeprefix("mock-video-")
        return NormalizedResult(
            ResultStatus.COMPLETED,
            self.provider_name,
            model.model,
            outputs=(ModelOutput(kind="asset", asset_ref=f"fixture://mock/video/{digest}.mp4"),),
            provider_request_id=provider_request_id,
            cost=CostEstimate(model.fixed_request_usd, CostConfidence.EXACT, "mock-v1"),
        )

    async def cancel(self, provider_request_id: str, model: ProviderModel) -> bool:
        del model
        return self._jobs.pop(provider_request_id, None) is not None

    def normalize_error(self, error: BaseException) -> ProviderCallError:
        if isinstance(error, ProviderCallError):
            return error
        return ProviderCallError(ErrorCategory.UNKNOWN, str(error), provider=self.provider_name)


def _synthesize(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or properties.keys())
        return {key: _synthesize(value) for key, value in sorted(properties.items()) if key in required}
    if schema_type == "array":
        return [_synthesize(schema.get("items") or {})]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema.get("enum"):
        return schema["enum"][0]
    return "mock"
