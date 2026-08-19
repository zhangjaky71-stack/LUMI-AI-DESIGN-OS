from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from .contracts import (
    ToolCallStatus,
    ToolPermissionContext,
    ToolRequest,
    ToolResult,
    canonical_json_bytes,
)

AUTH_SERVICE_HEADER = "X-Lumi-Service"
AUTH_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
AUTH_SIGNATURE_HEADER = "X-Lumi-Signature"
INVOKE_PATH = "/internal/v1/tools/invoke"
_CONTENT_TYPE = "application/json"
_DEFAULT_MAX_SKEW_SECONDS = 90
_DEFAULT_TIMEOUT_SECONDS = 130.0
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class InternalToolGatewayAuthError(ValueError):
    pass


class ToolGatewayHttpError(RuntimeError):
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
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_CALLER_FORBIDDEN")
    _validate_service(service)
    if timestamp is None:
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_TIMESTAMP_REQUIRED")
    try:
        parsed_timestamp = int(timestamp)
    except ValueError as exc:
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_TIMESTAMP_INVALID") from exc
    current = int(time.time()) if now is None else int(now)
    if max_skew_seconds < 1 or abs(current - parsed_timestamp) > max_skew_seconds:
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_TIMESTAMP_EXPIRED")
    if signature is None or len(signature) != 64:
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_SIGNATURE_INVALID")
    expected = hmac.new(
        secret_bytes,
        _canonical_auth_message(service, parsed_timestamp, method, path, body),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_SIGNATURE_INVALID")
    return service


def encode_tool_request(request: ToolRequest) -> dict[str, Any]:
    permission = request.permission_context
    return {
        "tool_call_id": str(request.tool_call_id),
        "organization_id": str(request.organization_id),
        "agent_run_id": str(request.agent_run_id),
        "task_id": str(request.task_id),
        "actor_agent": request.actor_agent,
        "name": request.name,
        "version": request.version,
        "arguments": request.arguments,
        "purpose": request.purpose,
        "permission_context": {
            "organization_id": str(permission.organization_id),
            "actor_id": permission.actor_id,
            "granted_permissions": sorted(permission.granted_permissions),
            "agent_allow_patterns": list(permission.agent_allow_patterns),
            "parent_allow_patterns": (
                list(permission.parent_allow_patterns)
                if permission.parent_allow_patterns is not None
                else None
            ),
            "organization_allow_patterns": list(permission.organization_allow_patterns),
            "organization_deny_patterns": list(permission.organization_deny_patterns),
        },
        "idempotency_key": request.idempotency_key,
        "approval_token": request.approval_token,
        "trace_id": request.trace_id,
    }


def decode_tool_request(payload: dict[str, Any]) -> ToolRequest:
    permission = _required_dict(payload, "permission_context")
    return ToolRequest(
        tool_call_id=UUID(_required_string(payload, "tool_call_id")),
        organization_id=UUID(_required_string(payload, "organization_id")),
        agent_run_id=UUID(_required_string(payload, "agent_run_id")),
        task_id=UUID(_required_string(payload, "task_id")),
        actor_agent=_required_string(payload, "actor_agent"),
        name=_required_string(payload, "name"),
        version=_required_string(payload, "version"),
        arguments=_required_dict(payload, "arguments"),
        purpose=_required_string(payload, "purpose"),
        permission_context=ToolPermissionContext(
            organization_id=UUID(_required_string(permission, "organization_id")),
            actor_id=_required_string(permission, "actor_id"),
            granted_permissions=frozenset(_string_list(permission, "granted_permissions")),
            agent_allow_patterns=tuple(_string_list(permission, "agent_allow_patterns")),
            parent_allow_patterns=(
                tuple(_string_list(permission, "parent_allow_patterns"))
                if permission.get("parent_allow_patterns") is not None
                else None
            ),
            organization_allow_patterns=tuple(
                _string_list(permission, "organization_allow_patterns")
            ),
            organization_deny_patterns=tuple(
                _string_list(permission, "organization_deny_patterns")
            ),
        ),
        idempotency_key=_optional_string(payload.get("idempotency_key")),
        approval_token=_optional_string(payload.get("approval_token")),
        trace_id=_optional_string(payload.get("trace_id")),
    )


def encode_tool_result(result: ToolResult) -> dict[str, Any]:
    return {
        "tool_call_id": str(result.tool_call_id),
        "status": result.status.value,
        "resolved_name": result.resolved_name,
        "resolved_version": result.resolved_version,
        "summary": result.summary,
        "data": result.data,
        "resource_refs": list(result.resource_refs),
        "truncated": result.truncated,
        "full_result_ref": result.full_result_ref,
        "replayed": result.replayed,
        "approval_id": result.approval_id,
        "error_code": result.error_code,
    }


def decode_tool_result(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        tool_call_id=UUID(_required_string(payload, "tool_call_id")),
        status=ToolCallStatus(_required_string(payload, "status")),
        resolved_name=_required_string(payload, "resolved_name"),
        resolved_version=_required_string(payload, "resolved_version"),
        summary=_optional_string(payload.get("summary")) or "",
        data=payload.get("data", {}),
        resource_refs=tuple(_string_list(payload, "resource_refs")),
        truncated=bool(payload.get("truncated", False)),
        full_result_ref=_optional_string(payload.get("full_result_ref")),
        replayed=bool(payload.get("replayed", False)),
        approval_id=_optional_string(payload.get("approval_id")),
        error_code=_optional_string(payload.get("error_code")),
    )


class HttpToolGatewayTransport:
    """Agent-facing private HTTP transport; Registry and adapters remain server-side."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        service: str = "agent-runtime",
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("TOOL_GATEWAY_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("TOOL_GATEWAY_URL_INVALID")
        if not 1.0 <= timeout_seconds <= 3600.0:
            raise ValueError("TOOL_GATEWAY_TIMEOUT_INVALID")
        if not 1024 <= max_response_bytes <= 16 * 1024 * 1024:
            raise ValueError("TOOL_GATEWAY_RESPONSE_LIMIT_INVALID")
        _secret_bytes(auth_secret)
        _validate_service(service)
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.service = service
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def invoke(self, request: ToolRequest) -> ToolResult:
        body = canonical_json_bytes(encode_tool_request(request))
        headers = sign_internal_request(
            secret=self.auth_secret,
            service=self.service,
            method="POST",
            path=INVOKE_PATH,
            body=body,
        ).as_dict()
        headers["Content-Type"] = _CONTENT_TYPE
        headers["Accept"] = _CONTENT_TYPE
        payload = await asyncio.to_thread(self._post, body, headers)
        return decode_tool_result(payload)

    def _post(self, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{INVOKE_PATH}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(self.max_response_bytes + 1)
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ToolGatewayHttpError(
                503,
                "TOOL_GATEWAY_UNAVAILABLE",
                "private Tool Gateway request failed",
            ) from exc
        if len(raw) > self.max_response_bytes:
            raise ToolGatewayHttpError(
                502,
                "TOOL_GATEWAY_RESPONSE_TOO_LARGE",
                "private Tool Gateway response exceeded limit",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolGatewayHttpError(
                502,
                "TOOL_GATEWAY_RESPONSE_INVALID",
                "private Tool Gateway returned invalid JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise ToolGatewayHttpError(
                502,
                "TOOL_GATEWAY_RESPONSE_INVALID",
                "private Tool Gateway response must be an object",
            )
        if not 200 <= status < 300:
            raise ToolGatewayHttpError(
                status,
                str(payload.get("code") or "TOOL_GATEWAY_HTTP_ERROR")[:128],
                str(payload.get("message") or "private Tool Gateway request failed")[:2000],
            )
        return payload


def _canonical_auth_message(
    service: str,
    timestamp: int,
    method: str,
    path: str,
    body: bytes,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{service}\n{timestamp}\n{method.upper()}\n{path}\n{body_hash}".encode("utf-8")


def _secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str) or len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_SECRET_INVALID")
    return secret.encode("utf-8")


def _validate_service(service: str) -> None:
    if not service or len(service) > 128:
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_SERVICE_INVALID")
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in service):
        raise InternalToolGatewayAuthError("TOOL_GATEWAY_AUTH_SERVICE_INVALID")


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"TOOL_GATEWAY_HTTP_FIELD_INVALID:{key}")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("TOOL_GATEWAY_HTTP_OPTIONAL_STRING_INVALID")
    return value


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"TOOL_GATEWAY_HTTP_FIELD_INVALID:{key}")
    return dict(value)


def _string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"TOOL_GATEWAY_HTTP_FIELD_INVALID:{key}")
    return list(value)
