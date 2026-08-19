from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from .models import (
    Capability,
    CostConfidence,
    CostEstimate,
    LatencyProfile,
    ModelOutput,
    ModelRequest,
    ModelResult,
    QualityProfile,
    ResultStatus,
    Timing,
    Usage,
)

AUTH_SERVICE_HEADER = "X-Lumi-Service"
AUTH_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
AUTH_SIGNATURE_HEADER = "X-Lumi-Signature"
_CONTENT_TYPE = "application/json"
_DEFAULT_MAX_SKEW_SECONDS = 90
_DEFAULT_TIMEOUT_SECONDS = 90.0


class InternalModelGatewayAuthError(ValueError):
    pass


class ModelGatewayHttpError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message[:2000])
        self.status = status
        self.code = code


@dataclass(frozen=True, slots=True)
class InternalAuthHeaders:
    service: str
    timestamp: int
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            AUTH_SERVICE_HEADER: self.service,
            AUTH_TIMESTAMP_HEADER: str(self.timestamp),
            AUTH_SIGNATURE_HEADER: self.signature,
        }


def sign_internal_request(
    *,
    secret: str,
    service: str,
    method: str,
    path: str,
    body: bytes,
    timestamp: int | None = None,
) -> InternalAuthHeaders:
    secret_bytes = _secret_bytes(secret)
    _validate_service(service)
    when = int(time.time()) if timestamp is None else int(timestamp)
    signature = hmac.new(
        secret_bytes,
        _canonical_auth_message(service, when, method, path, body),
        hashlib.sha256,
    ).hexdigest()
    return InternalAuthHeaders(service=service, timestamp=when, signature=signature)


def verify_internal_request(
    *,
    secret: str,
    allowed_services: frozenset[str],
    method: str,
    path: str,
    body: bytes,
    service: str | None,
    timestamp: str | None,
    signature: str | None,
    now: int | None = None,
    max_skew_seconds: int = _DEFAULT_MAX_SKEW_SECONDS,
) -> str:
    secret_bytes = _secret_bytes(secret)
    if service is None or service not in allowed_services:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_CALLER_FORBIDDEN")
    _validate_service(service)
    if timestamp is None:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_TIMESTAMP_REQUIRED")
    try:
        parsed_timestamp = int(timestamp)
    except ValueError as exc:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_TIMESTAMP_INVALID") from exc
    current = int(time.time()) if now is None else int(now)
    if max_skew_seconds < 1 or abs(current - parsed_timestamp) > max_skew_seconds:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_TIMESTAMP_EXPIRED")
    if signature is None or len(signature) != 64:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_SIGNATURE_INVALID")
    expected = hmac.new(
        secret_bytes,
        _canonical_auth_message(service, parsed_timestamp, method, path, body),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_SIGNATURE_INVALID")
    return service


def encode_model_request(request: ModelRequest) -> dict[str, Any]:
    return {
        "request_id": str(request.request_id),
        "organization_id": str(request.organization_id),
        "operation_id": str(request.operation_id),
        "project_id": str(request.project_id) if request.project_id else None,
        "task_id": str(request.task_id) if request.task_id else None,
        "agent_run_id": str(request.agent_run_id) if request.agent_run_id else None,
        "generation_id": str(request.generation_id) if request.generation_id else None,
        "capability": request.capability.value,
        "quality_profile": request.quality_profile.value,
        "latency_profile": request.latency_profile.value,
        "budget_limit_usd": (
            format(request.budget_limit_usd, "f")
            if request.budget_limit_usd is not None
            else None
        ),
        "inputs": _json_value(request.inputs),
        "structured_output_schema": _json_value(request.structured_output_schema),
        "reference_assets": list(request.reference_assets),
        "constraints": _json_value(request.constraints),
        "routing_hints": _json_value(request.routing_hints),
        "trace_id": request.trace_id,
    }


def decode_model_request(payload: dict[str, Any]) -> ModelRequest:
    return ModelRequest(
        request_id=UUID(_required_string(payload, "request_id")),
        organization_id=UUID(_required_string(payload, "organization_id")),
        operation_id=UUID(_required_string(payload, "operation_id")),
        project_id=_optional_uuid(payload.get("project_id")),
        task_id=_optional_uuid(payload.get("task_id")),
        agent_run_id=_optional_uuid(payload.get("agent_run_id")),
        generation_id=_optional_uuid(payload.get("generation_id")),
        capability=Capability(_required_string(payload, "capability")),
        quality_profile=QualityProfile(
            _optional_string(payload.get("quality_profile")) or QualityProfile.BALANCED.value
        ),
        latency_profile=LatencyProfile(
            _optional_string(payload.get("latency_profile")) or LatencyProfile.INTERACTIVE.value
        ),
        budget_limit_usd=_optional_decimal(payload.get("budget_limit_usd")),
        inputs=_required_dict(payload, "inputs"),
        structured_output_schema=_optional_dict(payload.get("structured_output_schema")),
        reference_assets=tuple(_required_string_list(payload.get("reference_assets", []))),
        constraints=_required_dict(payload, "constraints"),
        routing_hints=_required_dict(payload, "routing_hints"),
        trace_id=_optional_string(payload.get("trace_id")),
    )


def encode_model_result(result: ModelResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "provider": result.provider,
        "model": result.model,
        "provider_request_id": result.provider_request_id,
        "outputs": [
            {
                "kind": output.kind,
                "value": _json_value(output.value),
                "mime_type": output.mime_type,
            }
            for output in result.outputs
        ],
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
            "image_input_tokens": result.usage.image_input_tokens,
            "image_output_tokens": result.usage.image_output_tokens,
            "seconds": (
                format(result.usage.seconds, "f") if result.usage.seconds is not None else None
            ),
            "units": {key: format(value, "f") for key, value in result.usage.units.items()},
        },
        "timing": {
            "total_ms": result.timing.total_ms,
            "ttft_ms": result.timing.ttft_ms,
            "queue_ms": result.timing.queue_ms,
        },
        "cost": {
            "amount_usd": (
                format(result.cost.amount_usd, "f")
                if result.cost.amount_usd is not None
                else None
            ),
            "confidence": result.cost.confidence.value,
            "price_snapshot_id": result.cost.price_snapshot_id,
            "detail": _json_value(result.cost.detail),
        },
        "safety_metadata": _json_value(result.safety_metadata),
        "finish_reason": result.finish_reason,
        "raw_response_ref": result.raw_response_ref,
    }


def decode_model_result(payload: dict[str, Any]) -> ModelResult:
    usage_payload = _required_dict(payload, "usage")
    timing_payload = _required_dict(payload, "timing")
    cost_payload = _required_dict(payload, "cost")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        raise ValueError("MODEL_GATEWAY_HTTP_OUTPUTS_INVALID")
    outputs: list[ModelOutput] = []
    for raw in raw_outputs:
        if not isinstance(raw, dict):
            raise ValueError("MODEL_GATEWAY_HTTP_OUTPUT_INVALID")
        outputs.append(
            ModelOutput(
                kind=_required_string(raw, "kind"),
                value=raw.get("value"),
                mime_type=_optional_string(raw.get("mime_type")),
            )
        )
    raw_units = usage_payload.get("units", {})
    if not isinstance(raw_units, dict):
        raise ValueError("MODEL_GATEWAY_HTTP_USAGE_UNITS_INVALID")
    units = {str(key): Decimal(_string_value(value)) for key, value in raw_units.items()}
    raw_detail = cost_payload.get("detail", {})
    if not isinstance(raw_detail, dict):
        raise ValueError("MODEL_GATEWAY_HTTP_COST_DETAIL_INVALID")
    detail: dict[str, Decimal | int | str] = {}
    for key, value in raw_detail.items():
        if not isinstance(key, str):
            raise ValueError("MODEL_GATEWAY_HTTP_COST_DETAIL_KEY_INVALID")
        if isinstance(value, bool):
            detail[key] = str(value).lower()
        elif isinstance(value, int):
            detail[key] = value
        elif isinstance(value, str):
            try:
                detail[key] = Decimal(value)
            except Exception:
                detail[key] = value
        else:
            raise ValueError("MODEL_GATEWAY_HTTP_COST_DETAIL_VALUE_INVALID")
    return ModelResult(
        status=ResultStatus(_required_string(payload, "status")),
        provider=_required_string(payload, "provider"),
        model=_required_string(payload, "model"),
        provider_request_id=_optional_string(payload.get("provider_request_id")),
        outputs=tuple(outputs),
        usage=Usage(
            input_tokens=_optional_int(usage_payload.get("input_tokens")),
            output_tokens=_optional_int(usage_payload.get("output_tokens")),
            total_tokens=_optional_int(usage_payload.get("total_tokens")),
            cached_input_tokens=_optional_int(usage_payload.get("cached_input_tokens")),
            image_input_tokens=_optional_int(usage_payload.get("image_input_tokens")),
            image_output_tokens=_optional_int(usage_payload.get("image_output_tokens")),
            seconds=_optional_decimal(usage_payload.get("seconds")),
            units=units,
        ),
        timing=Timing(
            total_ms=_required_int(timing_payload, "total_ms"),
            ttft_ms=_optional_int(timing_payload.get("ttft_ms")),
            queue_ms=_optional_int(timing_payload.get("queue_ms")),
        ),
        cost=CostEstimate(
            amount_usd=_optional_decimal(cost_payload.get("amount_usd")),
            confidence=CostConfidence(_required_string(cost_payload, "confidence")),
            price_snapshot_id=_optional_string(cost_payload.get("price_snapshot_id")),
            detail=detail,
        ),
        safety_metadata=_required_dict(payload, "safety_metadata"),
        finish_reason=_optional_string(payload.get("finish_reason")),
        raw_response_ref=_optional_string(payload.get("raw_response_ref")),
    )


class HttpModelGatewayClient:
    """Provider-neutral signed client for the private Model Gateway service."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        caller_service: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("MODEL_GATEWAY_BASE_URL_INVALID")
        _secret_bytes(auth_secret)
        _validate_service(caller_service)
        if timeout_seconds <= 0:
            raise ValueError("MODEL_GATEWAY_HTTP_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.caller_service = caller_service
        self.timeout_seconds = timeout_seconds

    async def invoke(self, request: ModelRequest) -> ModelResult:
        payload = encode_model_request(request)
        body = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        path = "/internal/v1/models/invoke"
        auth = sign_internal_request(
            secret=self.auth_secret,
            service=self.caller_service,
            method="POST",
            path=path,
            body=body,
        )
        response_payload = await asyncio.to_thread(
            self._request,
            path,
            body,
            auth.as_dict(),
        )
        return decode_model_result(response_payload)

    def _request(
        self,
        path: str,
        body: bytes,
        auth_headers: dict[str, str],
    ) -> dict[str, Any]:
        headers = {"Content-Type": _CONTENT_TYPE, **auth_headers}
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = int(exc.code)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ModelGatewayHttpError(
                status,
                "MODEL_GATEWAY_HTTP_RESPONSE_INVALID",
                "model gateway returned a non-JSON response",
            ) from exc
        if not isinstance(payload, dict):
            raise ModelGatewayHttpError(
                status,
                "MODEL_GATEWAY_HTTP_RESPONSE_INVALID",
                "model gateway returned an invalid JSON object",
            )
        if not 200 <= status < 300:
            code = payload.get("code")
            message = payload.get("message")
            raise ModelGatewayHttpError(
                status,
                code if isinstance(code, str) else "MODEL_GATEWAY_HTTP_ERROR",
                message if isinstance(message, str) else "model gateway request failed",
            )
        return payload


def _canonical_auth_message(
    service: str,
    timestamp: int,
    method: str,
    path: str,
    body: bytes,
) -> bytes:
    if not path.startswith("/") or "\n" in path:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_PATH_INVALID")
    method_name = method.upper()
    if not method_name or "\n" in method_name:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_METHOD_INVALID")
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{service}\n{timestamp}\n{method_name}\n{path}\n{body_hash}".encode("utf-8")


def _secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_AUTH_SECRET_TOO_SHORT")
    return secret.encode("utf-8")


def _validate_service(service: str) -> None:
    if (
        not service
        or len(service) > 64
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in service)
    ):
        raise InternalModelGatewayAuthError("MODEL_GATEWAY_CALLER_INVALID")


def _json_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 24:
        raise ValueError("MODEL_GATEWAY_HTTP_JSON_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("MODEL_GATEWAY_HTTP_NON_FINITE_FLOAT")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("MODEL_GATEWAY_HTTP_NON_FINITE_DECIMAL")
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("MODEL_GATEWAY_HTTP_DICT_KEY_INVALID")
        return {
            key: _json_value(child, depth=depth + 1)
            for key, child in value.items()
        }
    raise ValueError(f"MODEL_GATEWAY_HTTP_VALUE_UNSUPPORTED:{type(value).__name__}")


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"MODEL_GATEWAY_HTTP_{key.upper()}_INVALID")
    return value


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"MODEL_GATEWAY_HTTP_{key.upper()}_INVALID")
    return value


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("MODEL_GATEWAY_HTTP_OPTIONAL_DICT_INVALID")
    return value


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"MODEL_GATEWAY_HTTP_{key.upper()}_INVALID")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("MODEL_GATEWAY_HTTP_OPTIONAL_INT_INVALID")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("MODEL_GATEWAY_HTTP_OPTIONAL_STRING_INVALID")
    return value


def _optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return UUID(_string_value(value))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise ValueError("MODEL_GATEWAY_HTTP_DECIMAL_FLOAT_FORBIDDEN")
    decimal_value = Decimal(_string_value(value))
    if not decimal_value.is_finite():
        raise ValueError("MODEL_GATEWAY_HTTP_DECIMAL_INVALID")
    return decimal_value


def _required_string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("MODEL_GATEWAY_HTTP_STRING_LIST_INVALID")
    return list(value)


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("MODEL_GATEWAY_HTTP_STRING_VALUE_INVALID")
    return value
