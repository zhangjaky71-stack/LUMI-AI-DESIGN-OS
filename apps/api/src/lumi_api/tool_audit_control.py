from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.persistence.models import AuditEvent

_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_SKEW_SECONDS = 90
_ALLOWED_CALLERS = frozenset({"tool-gateway"})
_SERVICE_HEADER = "X-Lumi-Service"
_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_SIGNATURE_HEADER = "X-Lumi-Signature"
_SECRET_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
)


class ToolAuditConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalToolAuditEvent:
    id: UUID
    organization_id: UUID
    actor_type: str
    actor_id: UUID | None
    action: str
    target_type: str
    target_id: UUID
    request_id: str | None
    metadata_json: dict[str, Any]


class ToolAuditWriter(Protocol):
    async def write(self, event: CanonicalToolAuditEvent) -> bool: ...


class SqlAlchemyToolAuditWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def write(self, event: CanonicalToolAuditEvent) -> bool:
        async with self._session_factory() as session:
            statement = (
                insert(AuditEvent)
                .values(
                    id=event.id,
                    organization_id=event.organization_id,
                    actor_type=event.actor_type,
                    actor_id=event.actor_id,
                    action=event.action,
                    target_type=event.target_type,
                    target_id=event.target_id,
                    request_id=event.request_id,
                    metadata_json=event.metadata_json,
                )
                .on_conflict_do_nothing(index_elements=[AuditEvent.id])
                .returning(AuditEvent.id)
            )
            inserted = (await session.execute(statement)).scalar_one_or_none()
            if inserted is not None:
                await session.commit()
                return True

            existing = (
                await session.execute(
                    select(AuditEvent.metadata_json).where(AuditEvent.id == event.id)
                )
            ).scalar_one_or_none()
            if not isinstance(existing, dict):
                raise ToolAuditConflictError("existing audit event cannot be verified")
            if existing.get("event_hash") != event.metadata_json.get("event_hash"):
                raise ToolAuditConflictError(
                    "audit event id was reused with different canonical content"
                )
            await session.commit()
            return False


@dataclass(frozen=True, slots=True)
class ToolAuditControlRuntime:
    writer: ToolAuditWriter
    auth_secret: str


def build_tool_audit_control_runtime(
    session_factory: async_sessionmaker[AsyncSession],
) -> ToolAuditControlRuntime:
    secret = os.getenv("LUMI_TOOL_AUDIT_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_TOOL_AUDIT_AUTH_SECRET_REQUIRED")
    return ToolAuditControlRuntime(
        writer=SqlAlchemyToolAuditWriter(session_factory),
        auth_secret=secret,
    )


def create_tool_audit_control_router(runtime: ToolAuditControlRuntime) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/tool-audit", tags=["internal-tool-audit"])

    @router.post("/events")
    async def write_event(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            event = _canonical_event(payload_or_error)
            created = await runtime.writer.write(event)
        except ToolAuditConflictError as exc:
            return _error(409, "TOOL_AUDIT_EVENT_CONFLICT", str(exc))
        except ValueError as exc:
            return _error(422, "TOOL_AUDIT_EVENT_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "TOOL_AUDIT_PERSISTENCE_UNAVAILABLE",
                "canonical audit persistence is unavailable",
            )
        return JSONResponse(
            status_code=201 if created else 200,
            content={
                "event_id": str(event.id),
                "status": "created" if created else "replayed",
            },
        )

    return router


def _canonical_event(payload: dict[str, Any]) -> CanonicalToolAuditEvent:
    event_id = UUID(_required_string(payload, "event_id", max_length=36))
    organization_id = UUID(_required_string(payload, "organization_id", max_length=36))
    tool_call_id = UUID(_required_string(payload, "tool_call_id", max_length=36))
    actor_id_raw = _required_string(payload, "actor_id", max_length=255)
    actor_agent = _required_string(payload, "actor_agent", max_length=150)
    resolved_tool = _required_string(payload, "resolved_tool", max_length=300)
    risk = _required_string(payload, "risk", max_length=64)
    purpose = _required_string(payload, "purpose", max_length=4000)
    status = _required_string(payload, "status", max_length=64)
    trace_id = _optional_string(payload.get("trace_id"), max_length=128)
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("TOOL_AUDIT_ARGUMENTS_INVALID")
    _require_redacted(arguments)

    replayed = payload.get("replayed", False)
    if not isinstance(replayed, bool):
        raise ValueError("TOOL_AUDIT_REPLAYED_INVALID")
    side_effect_operation_id = _optional_string(
        payload.get("side_effect_operation_id"),
        max_length=255,
    )
    approval_id = _optional_string(payload.get("approval_id"), max_length=255)
    error_code = _optional_string(payload.get("error_code"), max_length=128)

    canonical_payload: dict[str, Any] = {
        "event_id": str(event_id),
        "organization_id": str(organization_id),
        "tool_call_id": str(tool_call_id),
        "actor_id": actor_id_raw,
        "actor_agent": actor_agent,
        "resolved_tool": resolved_tool,
        "risk": risk,
        "purpose": purpose,
        "status": status,
        "trace_id": trace_id,
        "arguments": arguments,
        "replayed": replayed,
        "side_effect_operation_id": side_effect_operation_id,
        "approval_id": approval_id,
        "error_code": error_code,
    }
    event_hash = hashlib.sha256(_canonical_json(canonical_payload)).hexdigest()
    actor_uuid = _parse_uuid(actor_id_raw)
    metadata = {
        "schema_version": 1,
        "event_hash": event_hash,
        "actor_id_raw": actor_id_raw,
        "actor_agent": actor_agent,
        "resolved_tool": resolved_tool,
        "risk": risk,
        "purpose": purpose,
        "status": status,
        "arguments": arguments,
        "replayed": replayed,
        "side_effect_operation_id": side_effect_operation_id,
        "approval_id": approval_id,
        "error_code": error_code,
    }
    return CanonicalToolAuditEvent(
        id=event_id,
        organization_id=organization_id,
        actor_type="agent",
        actor_id=actor_uuid,
        action=f"tool.invoke.{status}"[:150],
        target_type="tool_call",
        target_id=tool_call_id,
        request_id=trace_id,
        metadata_json=metadata,
    )


async def _authenticated_json(
    request: Request,
    secret: str,
) -> dict[str, Any] | JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return _error(400, "TOOL_AUDIT_CONTENT_LENGTH_INVALID", "invalid content length")
        if parsed_length < 0 or parsed_length > _MAX_BODY_BYTES:
            return _error(413, "TOOL_AUDIT_REQUEST_TOO_LARGE", "request body is too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(413, "TOOL_AUDIT_REQUEST_TOO_LARGE", "request body is too large")
    auth_error = _verify_auth(request, body, secret)
    if auth_error is not None:
        return auth_error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(422, "TOOL_AUDIT_JSON_INVALID", str(exc))
    if not isinstance(payload, dict):
        return _error(422, "TOOL_AUDIT_OBJECT_REQUIRED", "request body must be an object")
    return dict(payload)


def _verify_auth(request: Request, body: bytes, secret: str) -> JSONResponse | None:
    service = request.headers.get(_SERVICE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(401, "TOOL_AUDIT_CALLER_FORBIDDEN", "internal authentication failed")
    try:
        timestamp = int(request.headers.get(_TIMESTAMP_HEADER) or "")
    except ValueError:
        return _error(401, "TOOL_AUDIT_TIMESTAMP_INVALID", "internal authentication failed")
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(401, "TOOL_AUDIT_TIMESTAMP_EXPIRED", "internal authentication failed")
    signature = request.headers.get(_SIGNATURE_HEADER)
    if signature is None or len(signature) != 64:
        return _error(401, "TOOL_AUDIT_SIGNATURE_INVALID", "internal authentication failed")
    body_hash = hashlib.sha256(body).hexdigest()
    message = (
        f"{service}\n{timestamp}\n{request.method.upper()}\n{request.url.path}\n{body_hash}"
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        return _error(401, "TOOL_AUDIT_SIGNATURE_INVALID", "internal authentication failed")
    return None


def _require_redacted(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = key.lower().replace("-", "_")
            if any(token in normalized_key for token in _SECRET_TOKENS):
                if child != "[REDACTED]":
                    raise ValueError(f"TOOL_AUDIT_SENSITIVE_FIELD_NOT_REDACTED:{key}")
                continue
            _require_redacted(child)
        return
    if isinstance(value, list):
        for child in value:
            _require_redacted(child)


def _required_string(payload: dict[str, Any], key: str, *, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ValueError(f"TOOL_AUDIT_FIELD_INVALID:{key}")
    return value


def _optional_string(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
        raise ValueError("TOOL_AUDIT_OPTIONAL_STRING_INVALID")
    return value


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
