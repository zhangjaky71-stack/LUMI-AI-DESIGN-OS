from __future__ import annotations

import json
from decimal import Decimal
from time import monotonic
from typing import Any

from .errors import ErrorCategory, ProviderCallError, UnsupportedProviderOperation
from .http_common import json_request
from .models import (
    Capability,
    CostConfidence,
    CostEstimate,
    InputKind,
    ModelOutput,
    ModelRequest,
    ModelTiming,
    ModelUsage,
    NormalizedResult,
    ProviderModel,
    ResultStatus,
)
from .ports import SecretProvider


class OpenAIResponsesAdapter:
    provider_name = "openai"

    def __init__(
        self,
        secrets: SecretProvider,
        *,
        model: str = "gpt-5.6",
        endpoint: str = "https://api.openai.com/v1/responses",
        input_usd_per_million: Decimal | None = None,
        output_usd_per_million: Decimal | None = None,
    ) -> None:
        self.secrets = secrets
        self.endpoint = endpoint.rstrip("/")
        self._models = (
            ProviderModel(
                provider=self.provider_name,
                model=model,
                capabilities=frozenset(
                    {
                        Capability.LLM_REASONING,
                        Capability.LLM_STRUCTURED_OUTPUT,
                        Capability.LLM_VISION,
                    }
                ),
                quality_score=92,
                latency_score=70,
                paid=True,
                input_usd_per_million=input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            ),
        )

    def models(self) -> tuple[ProviderModel, ...]:
        return self._models

    def validate(self, request: ModelRequest, model: ProviderModel) -> None:
        if request.capability not in model.capabilities:
            raise ValueError("requested capability is not supported by OpenAI model")
        for item in request.inputs:
            if item.kind in {InputKind.IMAGE, InputKind.DOCUMENT} and not item.uri:
                raise ValueError("OpenAI multimodal input requires URI")

    def estimate_cost(self, request: ModelRequest, model: ProviderModel) -> CostEstimate:
        if model.input_usd_per_million is None or model.output_usd_per_million is None:
            return CostEstimate(None, CostConfidence.UNKNOWN)
        estimated_input = int(request.constraints.get("estimated_input_tokens") or _estimate_input_tokens(request))
        estimated_output = int(request.constraints.get("max_output_tokens") or 1024)
        amount = (
            Decimal(estimated_input) * model.input_usd_per_million
            + Decimal(estimated_output) * model.output_usd_per_million
        ) / Decimal(1_000_000)
        return CostEstimate(amount, CostConfidence.ESTIMATED)

    async def invoke(self, request: ModelRequest, model: ProviderModel) -> NormalizedResult:
        self.validate(request, model)
        key = self.secrets.get_secret(self.provider_name, "api_key")
        payload: dict[str, Any] = {
            "model": model.model,
            "input": _openai_inputs(request),
            "store": False,
        }
        if request.structured_output_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "lumi_response",
                    "schema": request.structured_output_schema,
                    "strict": True,
                }
            }
        if request.constraints.get("max_output_tokens") is not None:
            payload["max_output_tokens"] = int(request.constraints["max_output_tokens"])
        started = monotonic()
        response = await json_request(
            provider=self.provider_name,
            method="POST",
            url=self.endpoint,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "X-Client-Request-Id": str(request.request_id),
            },
            payload=payload,
            timeout_seconds=float(request.constraints.get("provider_timeout_seconds") or 60),
        )
        total_ms = int((monotonic() - started) * 1000)
        return self._normalize(response.body, model, total_ms)

    async def stream(self, request: ModelRequest, model: ProviderModel):
        del request, model
        raise UnsupportedProviderOperation("OpenAI streaming transport is not enabled in NODE-22 v1")
        yield  # pragma: no cover

    async def get_async_status(self, provider_request_id: str, model: ProviderModel) -> NormalizedResult:
        key = self.secrets.get_secret(self.provider_name, "api_key")
        response = await json_request(
            provider=self.provider_name,
            method="GET",
            url=f"{self.endpoint}/{provider_request_id}",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        return self._normalize(response.body, model, 0)

    async def cancel(self, provider_request_id: str, model: ProviderModel) -> bool:
        del provider_request_id, model
        raise UnsupportedProviderOperation("OpenAI cancellation is not enabled for synchronous NODE-22 calls")

    def normalize_error(self, error: BaseException) -> ProviderCallError:
        if isinstance(error, ProviderCallError):
            return error
        return ProviderCallError(
            ErrorCategory.UNKNOWN,
            str(error),
            provider=self.provider_name,
            retryable=False,
        )

    def _normalize(self, data: dict[str, Any], model: ProviderModel, total_ms: int) -> NormalizedResult:
        status_value = str(data.get("status") or "completed")
        status = {
            "completed": ResultStatus.COMPLETED,
            "in_progress": ResultStatus.PENDING,
            "queued": ResultStatus.PENDING,
            "cancelled": ResultStatus.CANCELLED,
            "failed": ResultStatus.FAILED,
            "incomplete": ResultStatus.FAILED,
        }.get(status_value, ResultStatus.COMPLETED)
        text = _extract_output_text(data)
        outputs: list[ModelOutput] = []
        if text is not None:
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                outputs.append(ModelOutput(kind="text", text=text))
            else:
                outputs.append(ModelOutput(kind="json", json_value=parsed, text=text))
        usage_data = data.get("usage") or {}
        usage = ModelUsage(
            input_tokens=int(usage_data.get("input_tokens") or 0),
            output_tokens=int(usage_data.get("output_tokens") or 0),
            cached_input_tokens=int((usage_data.get("input_tokens_details") or {}).get("cached_tokens") or 0),
        )
        actual = _actual_cost(model, usage)
        return NormalizedResult(
            status=status,
            provider=self.provider_name,
            model=model.model,
            outputs=tuple(outputs),
            provider_request_id=str(data.get("id")) if data.get("id") else None,
            usage=usage,
            timing=ModelTiming(total_ms=total_ms),
            finish_reason=status_value,
            cost=actual,
        )


def _openai_inputs(request: ModelRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in request.inputs:
        if item.kind is InputKind.TEXT:
            messages.append({"role": item.role, "content": item.text or ""})
            continue
        content_type = "input_image" if item.kind is InputKind.IMAGE else "input_file"
        content: dict[str, Any] = {"type": content_type}
        if item.kind is InputKind.IMAGE:
            content["image_url"] = item.uri
        else:
            content["file_url"] = item.uri
        messages.append({"role": item.role, "content": [content]})
    return messages


def _extract_output_text(data: dict[str, Any]) -> str | None:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts) if parts else None


def _estimate_input_tokens(request: ModelRequest) -> int:
    characters = sum(len(item.text or "") for item in request.inputs)
    return max(1, characters // 4)


def _actual_cost(model: ProviderModel, usage: ModelUsage) -> CostEstimate:
    if model.input_usd_per_million is None or model.output_usd_per_million is None:
        return CostEstimate(None, CostConfidence.UNKNOWN)
    amount = (
        Decimal(usage.input_tokens) * model.input_usd_per_million
        + Decimal(usage.output_tokens) * model.output_usd_per_million
    ) / Decimal(1_000_000)
    return CostEstimate(amount, CostConfidence.EXACT)
