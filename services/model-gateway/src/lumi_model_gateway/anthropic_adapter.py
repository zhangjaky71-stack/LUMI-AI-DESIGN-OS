from __future__ import annotations

from collections.abc import AsyncIterator
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
    ModelStreamChunk,
    ModelTiming,
    ModelUsage,
    NormalizedResult,
    ProviderModel,
    ResultStatus,
)
from .ports import SecretProvider


class AnthropicMessagesAdapter:
    provider_name = "anthropic"

    def __init__(
        self,
        secrets: SecretProvider,
        *,
        model: str = "claude-sonnet-4-20250514",
        endpoint: str = "https://api.anthropic.com/v1/messages",
        input_usd_per_million: Decimal | None = None,
        output_usd_per_million: Decimal | None = None,
    ) -> None:
        self.secrets = secrets
        self.endpoint = endpoint
        self._models = (
            ProviderModel(
                provider=self.provider_name,
                model=model,
                capabilities=frozenset(
                    {Capability.LLM_REASONING, Capability.LLM_VISION}
                ),
                quality_score=88,
                latency_score=68,
                paid=True,
                input_usd_per_million=input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            ),
        )

    def models(self) -> tuple[ProviderModel, ...]:
        return self._models

    def validate(self, request: ModelRequest, model: ProviderModel) -> None:
        if request.capability not in model.capabilities:
            raise ValueError(
                "requested capability is not supported by Anthropic model"
            )
        if request.structured_output_schema is not None:
            raise ValueError(
                "Anthropic structured-output mapping is not claimed in NODE-22"
            )

    def estimate_cost(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> CostEstimate:
        if (
            model.input_usd_per_million is None
            or model.output_usd_per_million is None
        ):
            return CostEstimate(None, CostConfidence.UNKNOWN)
        characters = sum(len(item.text or "") for item in request.inputs)
        estimated_input = int(
            request.constraints.get("estimated_input_tokens")
            or max(1, characters // 4)
        )
        estimated_output = int(
            request.constraints.get("max_output_tokens") or 1024
        )
        amount = (
            Decimal(estimated_input) * model.input_usd_per_million
            + Decimal(estimated_output) * model.output_usd_per_million
        ) / Decimal(1_000_000)
        return CostEstimate(amount, CostConfidence.ESTIMATED)

    async def invoke(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> NormalizedResult:
        self.validate(request, model)
        key = self.secrets.get_secret(self.provider_name, "api_key")
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for item in request.inputs:
            if (
                item.role in {"system", "developer"}
                and item.kind is InputKind.TEXT
            ):
                system_parts.append(item.text or "")
                continue
            if item.kind is InputKind.TEXT:
                role = item.role if item.role in {"user", "assistant"} else "user"
                messages.append({"role": role, "content": item.text or ""})
            elif item.kind is InputKind.IMAGE:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": item.uri,
                                },
                            }
                        ],
                    }
                )
            else:
                raise ValueError(
                    "document URI mapping is not enabled for Anthropic NODE-22"
                )
        payload: dict[str, Any] = {
            "model": model.model,
            "max_tokens": int(
                request.constraints.get("max_output_tokens") or 1024
            ),
            "messages": messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        started = monotonic()
        response = await json_request(
            provider=self.provider_name,
            method="POST",
            url=self.endpoint,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload=payload,
            timeout_seconds=float(
                request.constraints.get("provider_timeout_seconds") or 60
            ),
        )
        total_ms = int((monotonic() - started) * 1000)
        data = response.body
        text_parts = [
            block.get("text", "")
            for block in data.get("content") or []
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        usage_data = data.get("usage") or {}
        usage = ModelUsage(
            input_tokens=int(usage_data.get("input_tokens") or 0),
            output_tokens=int(usage_data.get("output_tokens") or 0),
            cached_input_tokens=int(
                usage_data.get("cache_read_input_tokens") or 0
            ),
        )
        return NormalizedResult(
            status=ResultStatus.COMPLETED,
            provider=self.provider_name,
            model=model.model,
            outputs=(ModelOutput(kind="text", text="".join(text_parts)),),
            provider_request_id=(
                str(data.get("id")) if data.get("id") else None
            ),
            usage=usage,
            timing=ModelTiming(total_ms=total_ms),
            finish_reason=(
                str(data.get("stop_reason"))
                if data.get("stop_reason")
                else None
            ),
            cost=_actual_cost(model, usage),
        )

    async def stream(
        self,
        request: ModelRequest,
        model: ProviderModel,
    ) -> AsyncIterator[ModelStreamChunk]:
        del request, model
        raise UnsupportedProviderOperation(
            "Anthropic streaming transport is not enabled in NODE-22 v1"
        )
        yield  # pragma: no cover

    async def get_async_status(
        self,
        provider_request_id: str,
        model: ProviderModel,
    ) -> NormalizedResult:
        del provider_request_id, model
        raise UnsupportedProviderOperation(
            "Anthropic Messages calls are synchronous in NODE-22 v1"
        )

    async def cancel(
        self,
        provider_request_id: str,
        model: ProviderModel,
    ) -> bool:
        del provider_request_id, model
        raise UnsupportedProviderOperation(
            "Anthropic cancellation is not enabled in NODE-22 v1"
        )

    def normalize_error(self, error: BaseException) -> ProviderCallError:
        if isinstance(error, ProviderCallError):
            return error
        return ProviderCallError(
            ErrorCategory.UNKNOWN,
            str(error),
            provider=self.provider_name,
        )


def _actual_cost(model: ProviderModel, usage: ModelUsage) -> CostEstimate:
    if (
        model.input_usd_per_million is None
        or model.output_usd_per_million is None
    ):
        return CostEstimate(None, CostConfidence.UNKNOWN)
    amount = (
        Decimal(usage.input_tokens) * model.input_usd_per_million
        + Decimal(usage.output_tokens) * model.output_usd_per_million
    ) / Decimal(1_000_000)
    return CostEstimate(amount, CostConfidence.EXACT)
