from __future__ import annotations

import asyncio
import json
import os
import socket
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from .errors import (
    DeliveryState,
    ErrorCategory,
    ProviderInvocationError,
    ProviderValidationError,
)
from .models import (
    Capability,
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

_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_OPENAI_POLICY_CODES = frozenset(
    {
        "content_policy_violation",
        "safety_policy_violation",
        "moderation_blocked",
    }
)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse: ...


class UrllibHttpTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    status=int(response.status),
                    headers={
                        key.lower(): value for key, value in response.headers.items()
                    },
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status=exc.code,
                headers={key.lower(): value for key, value in exc.headers.items()},
                body=exc.read(),
            )


class OpenAIResponsesAdapter:
    """Server-side OpenAI Responses adapter with no OpenAI SDK dependency."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        price_card: PriceCard,
        transport: HttpTransport | None = None,
        organization: str | None = None,
        project: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY_REQUIRED")
        if not model:
            raise ValueError("OPENAI_MODEL_REQUIRED")
        if timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_INVALID")
        self._api_key = api_key
        self._organization = organization
        self._project = project
        self._transport = transport or UrllibHttpTransport()
        self._timeout_seconds = timeout_seconds
        self._price_card = price_card
        self._descriptor = ProviderModel(
            provider="openai",
            model=model,
            capabilities=frozenset(
                {
                    Capability.LLM_REASONING,
                    Capability.LLM_STRUCTURED_OUTPUT,
                }
            ),
            quality_score=92,
            latency_class=ProviderLatencyClass.STANDARD,
            supports_streaming=False,
            supports_async=False,
        )

    @classmethod
    def from_env(
        cls,
        *,
        transport: HttpTransport | None = None,
    ) -> OpenAIResponsesAdapter:
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "")
        snapshot_id = os.getenv("OPENAI_PRICE_SNAPSHOT_ID", "openai-env-price")
        price_card = PriceCard(
            snapshot_id=snapshot_id,
            input_usd_per_million_tokens=_optional_decimal(
                os.getenv("OPENAI_INPUT_USD_PER_1M_TOKENS")
            ),
            output_usd_per_million_tokens=_optional_decimal(
                os.getenv("OPENAI_OUTPUT_USD_PER_1M_TOKENS")
            ),
        )
        return cls(
            api_key=api_key,
            model=model,
            price_card=price_card,
            transport=transport,
            organization=os.getenv("OPENAI_ORGANIZATION"),
            project=os.getenv("OPENAI_PROJECT"),
        )

    @property
    def descriptor(self) -> ProviderModel:
        return self._descriptor

    def __repr__(self) -> str:
        return f"OpenAIResponsesAdapter(model={self._descriptor.model!r})"

    def validate(self, request: ModelRequest) -> None:
        if request.capability not in self._descriptor.capabilities:
            raise ProviderValidationError(
                ErrorCategory.INVALID_REQUEST,
                "OpenAI Responses adapter does not expose this capability",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        if request.reference_assets:
            raise ProviderValidationError(
                ErrorCategory.HARD_CONSTRAINT_INVALID,
                "reference assets require a vision/image adapter, not this text adapter",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        self._format_input(request)
        if (
            request.capability == Capability.LLM_STRUCTURED_OUTPUT
            and request.structured_output_schema is None
        ):
            raise ProviderValidationError(
                ErrorCategory.INVALID_REQUEST,
                "structured output requires structured_output_schema",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        max_output_tokens = request.constraints.get("max_output_tokens")
        if max_output_tokens is not None:
            if (
                not isinstance(max_output_tokens, int)
                or not 1 <= max_output_tokens <= 100_000
            ):
                raise ProviderValidationError(
                    ErrorCategory.HARD_CONSTRAINT_INVALID,
                    "max_output_tokens must be an integer between 1 and 100000",
                    provider=self._descriptor.provider,
                    model=self._descriptor.model,
                    delivery_state=DeliveryState.NOT_ACCEPTED,
                )

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate:
        self.validate(request)
        return self._price_card.estimate(request)

    async def invoke(self, request: ModelRequest) -> ModelResult:
        self.validate(request)
        encoded = json.dumps(
            self._payload(request),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
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
                url=_OPENAI_RESPONSES_URL,
                headers=headers,
                body=encoded,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        elapsed_ms = int((loop.time() - started) * 1000)
        if not 200 <= response.status < 300:
            raise self._http_error(response)
        return self._parse_response(
            request,
            response.body,
            elapsed_ms=elapsed_ms,
        )

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        async def unsupported() -> AsyncIterator[StreamChunk]:
            raise ProviderInvocationError(
                ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
                "OpenAI streaming transport is not enabled in the NODE-22 adapter",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
            yield StreamChunk(
                request_id=request.request_id,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                sequence=0,
                kind="unreachable",
            )

        return unsupported()

    async def get_async_status(self, provider_request_id: str) -> ModelResult:
        del provider_request_id
        raise ProviderInvocationError(
            ErrorCategory.INVALID_REQUEST,
            "this adapter uses synchronous Responses requests with store=false",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    async def cancel(self, provider_request_id: str) -> ModelResult:
        del provider_request_id
        raise ProviderInvocationError(
            ErrorCategory.INVALID_REQUEST,
            "this adapter does not start cancellable background Responses requests",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    def normalize_error(self, error: Exception) -> ProviderInvocationError:
        if isinstance(error, ProviderInvocationError):
            return error
        if isinstance(error, (TimeoutError, socket.timeout)):
            return ProviderInvocationError(
                ErrorCategory.TIMEOUT,
                "OpenAI request timed out",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.UNKNOWN,
            )
        if isinstance(error, urllib.error.URLError):
            return ProviderInvocationError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "OpenAI network request failed",
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

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._descriptor.model,
            "input": self._format_input(request),
            "store": False,
        }
        max_output_tokens = request.constraints.get("max_output_tokens")
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        if request.capability == Capability.LLM_STRUCTURED_OUTPUT:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "lumi_response",
                    "schema": request.structured_output_schema,
                    "strict": True,
                }
            }
        return payload

    def _format_input(
        self,
        request: ModelRequest,
    ) -> str | list[dict[str, str]]:
        prompt = request.inputs.get("prompt")
        messages = request.inputs.get("messages")
        if isinstance(prompt, str) and prompt.strip() and messages is None:
            return prompt
        if isinstance(messages, list) and messages and prompt is None:
            formatted: list[dict[str, str]] = []
            allowed_roles = {"developer", "system", "user", "assistant"}
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    raise self._input_error(f"messages[{index}] must be an object")
                if set(message) - {"role", "content"}:
                    raise self._input_error(
                        f"messages[{index}] contains provider-native/unknown fields"
                    )
                role = message.get("role")
                content = message.get("content")
                if role not in allowed_roles or not isinstance(content, str):
                    raise self._input_error(
                        f"messages[{index}] requires a supported role and string content"
                    )
                formatted.append({"role": str(role), "content": content})
            return formatted
        raise self._input_error("inputs must contain exactly one of prompt or messages")

    def _input_error(self, message: str) -> ProviderValidationError:
        return ProviderValidationError(
            ErrorCategory.INVALID_REQUEST,
            message,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    def _http_error(self, response: HttpResponse) -> ProviderInvocationError:
        category = ErrorCategory.UNKNOWN
        delivery_state = DeliveryState.UNKNOWN
        message, provider_code = _extract_error(response.body)
        if provider_code in _OPENAI_POLICY_CODES:
            category = ErrorCategory.USER_CONTENT_POLICY_BLOCK
            delivery_state = DeliveryState.NOT_ACCEPTED
        elif response.status in {401, 403}:
            category = ErrorCategory.AUTH_ERROR
            delivery_state = DeliveryState.NOT_ACCEPTED
        elif response.status == 429:
            category = ErrorCategory.RATE_LIMIT
            delivery_state = DeliveryState.NOT_ACCEPTED
        elif response.status in {400, 404, 409, 422}:
            category = ErrorCategory.INVALID_REQUEST
            delivery_state = DeliveryState.NOT_ACCEPTED
        elif response.status == 408:
            category = ErrorCategory.TIMEOUT
        elif 500 <= response.status <= 599:
            category = ErrorCategory.PROVIDER_5XX
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        return ProviderInvocationError(
            category,
            message or f"OpenAI HTTP {response.status}",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=delivery_state,
            retry_after_seconds=retry_after,
            provider_code=provider_code,
        )

    def _parse_response(
        self,
        request: ModelRequest,
        body: bytes,
        *,
        elapsed_ms: int,
    ) -> ModelResult:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI returned invalid JSON",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.ACCEPTED,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI returned an invalid response object",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.ACCEPTED,
            )
        status = str(payload.get("status", "completed"))
        if status == "failed":
            error_payload = payload.get("error")
            message = "OpenAI response failed"
            provider_code = None
            if isinstance(error_payload, dict):
                message = str(error_payload.get("message") or message)
                provider_code = _optional_text(error_payload.get("code"))
            category = (
                ErrorCategory.USER_CONTENT_POLICY_BLOCK
                if provider_code in _OPENAI_POLICY_CODES
                else ErrorCategory.PROVIDER_5XX
            )
            raise ProviderInvocationError(
                category,
                message,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.ACCEPTED,
                provider_code=provider_code,
            )
        outputs, refused = self._outputs(request, payload)
        usage = _usage(payload.get("usage"))
        cost = self._price_card.actual_from_usage(request.capability, usage)
        result_status = {
            "completed": ResultStatus.SUCCEEDED,
            "in_progress": ResultStatus.PENDING,
            "queued": ResultStatus.PENDING,
            "cancelled": ResultStatus.CANCELLED,
            "incomplete": ResultStatus.SUCCEEDED,
        }.get(status, ResultStatus.SUCCEEDED)
        finish_reason = status
        incomplete = payload.get("incomplete_details")
        if isinstance(incomplete, dict) and incomplete.get("reason"):
            finish_reason = str(incomplete["reason"])
        return ModelResult(
            status=result_status,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            provider_request_id=_optional_text(payload.get("id")),
            outputs=outputs,
            usage=usage,
            timing=Timing(total_ms=elapsed_ms),
            cost=cost,
            safety_metadata={"refused": refused},
            finish_reason=finish_reason,
            raw_response_ref=None,
        )

    def _outputs(
        self,
        request: ModelRequest,
        payload: dict[str, Any],
    ) -> tuple[tuple[ModelOutput, ...], bool]:
        texts: list[str] = []
        refusals: list[str] = []
        raw_output = payload.get("output", [])
        if isinstance(raw_output, list):
            for item in raw_output:
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                content = item.get("content", [])
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if (
                        part.get("type") == "output_text"
                        and isinstance(part.get("text"), str)
                    ):
                        texts.append(part["text"])
                    if (
                        part.get("type") == "refusal"
                        and isinstance(part.get("refusal"), str)
                    ):
                        refusals.append(part["refusal"])
        combined = "".join(texts)
        if request.capability == Capability.LLM_STRUCTURED_OUTPUT and combined:
            try:
                value = json.loads(combined)
            except json.JSONDecodeError as exc:
                raise ProviderInvocationError(
                    ErrorCategory.UNKNOWN,
                    "OpenAI structured output was not valid JSON",
                    provider=self._descriptor.provider,
                    model=self._descriptor.model,
                    delivery_state=DeliveryState.ACCEPTED,
                ) from exc
            return (
                (
                    ModelOutput(
                        kind="json",
                        value=value,
                        mime_type="application/json",
                    ),
                ),
                bool(refusals),
            )
        outputs: list[ModelOutput] = []
        if combined:
            outputs.append(
                ModelOutput(
                    kind="text",
                    value=combined,
                    mime_type="text/plain",
                )
            )
        if refusals:
            outputs.append(
                ModelOutput(
                    kind="refusal",
                    value="\n".join(refusals),
                    mime_type="text/plain",
                )
            )
        return tuple(outputs), bool(refusals)


def _usage(value: Any) -> Usage:
    if not isinstance(value, dict):
        return Usage()
    details = value.get("input_tokens_details")
    cached_tokens = details.get("cached_tokens") if isinstance(details, dict) else None
    return Usage(
        input_tokens=_optional_int(value.get("input_tokens")),
        output_tokens=_optional_int(value.get("output_tokens")),
        total_tokens=_optional_int(value.get("total_tokens")),
        cached_input_tokens=_optional_int(cached_tokens),
    )


def _extract_error(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None, None
    return _optional_text(error.get("message")), _optional_text(error.get("code"))


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        return max(0.0, (target - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("OPENAI_PRICE_RATE_INVALID") from exc


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None
