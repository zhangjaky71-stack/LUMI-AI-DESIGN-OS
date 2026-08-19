from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lumi_api.idempotency import (
    IdempotencyContext,
    SideEffectGateway,
    SideEffectResult,
)

_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_SKEW_SECONDS = 90
_ALLOWED_CALLERS = frozenset({"tool-gateway"})
_SERVICE_HEADER = "X-Lumi-Service"
_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_SIGNATURE_HEADER = "X-Lumi-Signature"


@dataclass(frozen=True, slots=True)
class ToolSideEffectControlRuntime:
    gateway: SideEffectGateway
    auth_secret: str


def build_tool_side_effect_control_runtime(
    database_url: str,
) -> ToolSideEffectControlRuntime:
    secret = os.getenv("LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET_REQUIRED")
    return ToolSideEffectControlRuntime(
        gateway=SideEffectGateway(database_url),
        auth_secret=secret,
    )


def create_tool_side_effect_control_router(
    runtime: ToolSideEffectControlRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/side-effects", tags=["internal-side-effects"])

    @router.post("/claim")
    async def claim(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        try:
            business_scope_raw = payload.get("business_scope_id")
            context = IdempotencyContext(
                organization_id=UUID(_required_string(payload, "organization_id")),
                operation_type=_required_string(payload, "operation_type"),
                idempotency_key=_required_string(payload, "idempotency_key"),
                request=payload.get("request", {}),
                business_scope_id=(
                    UUID(business_scope_raw)
                    if isinstance(business_scope_raw, str) and business_scope_raw
                    else None
                ),
                lease_seconds=_bounded_int(payload.get("lease_seconds", 120), 5, 3600),
            )
            lease_owner = _required_string(payload, "lease_owner", max_length=200)
            result = await runtime.gateway.claim(context, lease_owner=lease_owner)
        except ValueError as exc:
            return _error(422, "SIDE_EFFECT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception as exc:
            code = getattr(exc, "code", "SIDE_EFFECT_CONTROL_CLAIM_FAILED")
            status = int(getattr(exc, "http_status", 409))
            return _error(status, str(code), str(exc))
        snapshot = result.snapshot
        return JSONResponse(
            status_code=200,
            content={
                "decision": result.decision.value,
                "operation_id": str(snapshot.id),
                "status": snapshot.status.value,
                "result_ref": snapshot.result_ref,
                "result_json": snapshot.result_json,
                "response_status": snapshot.response_status,
                "error_code": snapshot.error_code,
                "ambiguity_reason": snapshot.ambiguity_reason,
            },
        )

    @router.post("/{operation_id}/attempt")
    async def mark_attempt(operation_id: str, request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            await runtime.gateway.mark_provider_attempt_started(
                UUID(operation_id),
                lease_owner=_required_string(
                    payload_or_error,
                    "lease_owner",
                    max_length=200,
                ),
            )
        except ValueError as exc:
            return _error(422, "SIDE_EFFECT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception as exc:
            return _error(
                409,
                str(getattr(exc, "code", "SIDE_EFFECT_CONTROL_ATTEMPT_FAILED")),
                str(exc),
            )
        return JSONResponse(status_code=200, content={"status": "attempt_started"})

    @router.post("/{operation_id}/succeed")
    async def succeed(operation_id: str, request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        try:
            result_json = payload.get("result_json", {})
            if not isinstance(result_json, dict):
                raise ValueError("SIDE_EFFECT_RESULT_JSON_INVALID")
            await runtime.gateway.succeed(
                UUID(operation_id),
                lease_owner=_required_string(payload, "lease_owner", max_length=200),
                result=SideEffectResult(
                    result_ref=_optional_string(
                        payload.get("result_ref"),
                        max_length=2048,
                    ),
                    result_json=result_json,
                    response_status=_bounded_int(
                        payload.get("response_status", 200),
                        100,
                        599,
                    ),
                ),
            )
        except ValueError as exc:
            return _error(422, "SIDE_EFFECT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception as exc:
            return _error(
                409,
                str(getattr(exc, "code", "SIDE_EFFECT_CONTROL_SUCCEED_FAILED")),
                str(exc),
            )
        return JSONResponse(status_code=200, content={"status": "succeeded"})

    @router.post("/{operation_id}/ambiguous")
    async def ambiguous(operation_id: str, request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        try:
            await runtime.gateway.mark_ambiguous(
                UUID(operation_id),
                lease_owner=_required_string(payload, "lease_owner", max_length=200),
                reason=_required_string(payload, "reason", max_length=2000),
            )
        except ValueError as exc:
            return _error(422, "SIDE_EFFECT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception as exc:
            return _error(
                409,
                str(getattr(exc, "code", "SIDE_EFFECT_CONTROL_AMBIGUOUS_FAILED")),
                str(exc),
            )
        return JSONResponse(status_code=200, content={"status": "ambiguous"})

    return router


async def _authenticated_json(
    request: Request,
    secret: str,
) -> dict[str, Any] | JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return _error(
                400,
                "SIDE_EFFECT_CONTROL_CONTENT_LENGTH_INVALID",
                "invalid content length",
            )
        if parsed_length < 0 or parsed_length > _MAX_BODY_BYTES:
            return _error(
                413,
                "SIDE_EFFECT_CONTROL_REQUEST_TOO_LARGE",
                "request body is too large",
            )
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(
            413,
            "SIDE_EFFECT_CONTROL_REQUEST_TOO_LARGE",
            "request body is too large",
        )
    auth_error = _verify_auth(request, body, secret)
    if auth_error is not None:
        return auth_error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(422, "SIDE_EFFECT_CONTROL_JSON_INVALID", str(exc))
    if not isinstance(payload, dict):
        return _error(
            422,
            "SIDE_EFFECT_CONTROL_OBJECT_REQUIRED",
            "request body must be an object",
        )
    return dict(payload)


def _verify_auth(request: Request, body: bytes, secret: str) -> JSONResponse | None:
    service = request.headers.get(_SERVICE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(
            401,
            "SIDE_EFFECT_CONTROL_CALLER_FORBIDDEN",
            "internal authentication failed",
        )
    timestamp_raw = request.headers.get(_TIMESTAMP_HEADER)
    try:
        timestamp = int(timestamp_raw or "")
    except ValueError:
        return _error(
            401,
            "SIDE_EFFECT_CONTROL_TIMESTAMP_INVALID",
            "internal authentication failed",
        )
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(
            401,
            "SIDE_EFFECT_CONTROL_TIMESTAMP_EXPIRED",
            "internal authentication failed",
        )
    signature = request.headers.get(_SIGNATURE_HEADER)
    if signature is None or len(signature) != 64:
        return _error(
            401,
            "SIDE_EFFECT_CONTROL_SIGNATURE_INVALID",
            "internal authentication failed",
        )
    body_hash = hashlib.sha256(body).hexdigest()
    message = (
        f"{service}\n{timestamp}\n{request.method.upper()}\n{request.url.path}\n{body_hash}"
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        return _error(
            401,
            "SIDE_EFFECT_CONTROL_SIGNATURE_INVALID",
            "internal authentication failed",
        )
    return None


def _required_string(
    payload: dict[str, Any],
    key: str,
    *,
    max_length: int = 512,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ValueError(f"SIDE_EFFECT_CONTROL_FIELD_INVALID:{key}")
    return value


def _optional_string(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
        raise ValueError("SIDE_EFFECT_CONTROL_OPTIONAL_STRING_INVALID")
    return value


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("SIDE_EFFECT_CONTROL_INTEGER_INVALID")
    if not minimum <= value <= maximum:
        raise ValueError("SIDE_EFFECT_CONTROL_INTEGER_INVALID")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
