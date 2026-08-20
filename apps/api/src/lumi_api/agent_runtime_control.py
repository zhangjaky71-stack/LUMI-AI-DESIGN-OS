from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.idempotency.contracts import IdempotencyContext, SideEffectResult
from lumi_api.idempotency.gateway import IdempotencyError, SideEffectGateway
from lumi_api.persistence.models import AgentRun, Approval, OutboxEvent

_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_SKEW_SECONDS = 90
_ALLOWED_CALLERS = frozenset({"agent-runtime"})
_SERVICE_HEADER = "X-Lumi-Service"
_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_SIGNATURE_HEADER = "X-Lumi-Signature"
_EVENT_NAMESPACE = uuid5(NAMESPACE_URL, "lumi-agent-runtime-control-events-v1")


@dataclass(frozen=True, slots=True)
class AgentRuntimeControlRuntime:
    gateway: SideEffectGateway
    session_factory: async_sessionmaker[AsyncSession]
    auth_secret: str


def build_agent_runtime_control_runtime(
    *,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> AgentRuntimeControlRuntime:
    secret = os.getenv("LUMI_AGENT_CONTROL_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_AGENT_CONTROL_AUTH_SECRET_REQUIRED")
    if not database_url:
        raise RuntimeError("LUMI_DATABASE_URL_REQUIRED_FOR_AGENT_CONTROL")
    return AgentRuntimeControlRuntime(
        gateway=SideEffectGateway(database_url),
        session_factory=session_factory,
        auth_secret=secret,
    )


def create_agent_runtime_control_router(runtime: AgentRuntimeControlRuntime) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/agent-control", tags=["internal-agent-control"])

    @router.post("/probe")
    async def probe(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        if payload_or_error:
            return _error(422, "AGENT_CONTROL_PROBE_BODY_INVALID", "probe body must be empty")
        try:
            async with runtime.session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_PERSISTENCE_UNAVAILABLE",
                "canonical persistence is unavailable",
            )
        return JSONResponse(status_code=200, content={"status": "ok", "schema_version": 1})

    @router.post("/operations/claim")
    async def claim_operation(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            payload = payload_or_error
            organization_id = UUID(_required_string(payload, "organization_id", 36))
            operation_id = UUID(_required_string(payload, "operation_id", 36))
            operation_type = _required_string(payload, "operation_type", 100)
            request_hash = _required_hash(payload, "request_hash")
            lease_owner = _required_string(payload, "lease_owner", 200)
            claim = await runtime.gateway.claim(
                IdempotencyContext(
                    organization_id=organization_id,
                    operation_type=operation_type,
                    idempotency_key=str(operation_id),
                    request={"control_plane_request_hash": request_hash},
                    business_scope_id=operation_id,
                    lease_seconds=60,
                ),
                lease_owner=lease_owner,
            )
        except IdempotencyError as exc:
            return _error(exc.http_status, exc.code, "agent control operation was rejected")
        except (ValueError, TypeError) as exc:
            return _error(422, "AGENT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_IDEMPOTENCY_UNAVAILABLE",
                "canonical idempotency persistence is unavailable",
            )
        snapshot = claim.snapshot
        return JSONResponse(
            status_code=200,
            content={
                "decision": claim.decision.value,
                "ledger_operation_id": str(snapshot.id),
                "lease_owner": snapshot.lease_owner,
                "result_json": snapshot.result_json,
                "response_status": snapshot.response_status,
                "error_code": snapshot.error_code,
            },
        )

    @router.post("/operations/succeed")
    async def succeed_operation(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            payload = payload_or_error
            ledger_operation_id = UUID(_required_string(payload, "ledger_operation_id", 36))
            lease_owner = _required_string(payload, "lease_owner", 200)
            snapshot = payload.get("snapshot")
            if not isinstance(snapshot, dict):
                raise ValueError("AGENT_CONTROL_SNAPSHOT_INVALID")
            await runtime.gateway.succeed(
                ledger_operation_id,
                lease_owner=lease_owner,
                result=SideEffectResult(
                    result_json={"schema_version": 1, "snapshot": dict(snapshot)},
                    response_status=200,
                ),
            )
        except IdempotencyError as exc:
            return _error(exc.http_status, exc.code, "agent control success could not be committed")
        except (ValueError, TypeError) as exc:
            return _error(422, "AGENT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_IDEMPOTENCY_UNAVAILABLE",
                "canonical idempotency persistence is unavailable",
            )
        return JSONResponse(status_code=200, content={"status": "succeeded"})

    @router.post("/operations/fail-final")
    async def fail_final_operation(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            payload = payload_or_error
            ledger_operation_id = UUID(_required_string(payload, "ledger_operation_id", 36))
            lease_owner = _required_string(payload, "lease_owner", 200)
            error_code = _required_string(payload, "error_code", 64)
            await runtime.gateway.fail_final(
                ledger_operation_id,
                lease_owner=lease_owner,
                error_code=error_code,
            )
        except IdempotencyError as exc:
            return _error(exc.http_status, exc.code, "agent control failure could not be committed")
        except (ValueError, TypeError) as exc:
            return _error(422, "AGENT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_IDEMPOTENCY_UNAVAILABLE",
                "canonical idempotency persistence is unavailable",
            )
        return JSONResponse(status_code=200, content={"status": "failed_final"})

    @router.post("/operations/ambiguous")
    async def ambiguous_operation(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            payload = payload_or_error
            ledger_operation_id = UUID(_required_string(payload, "ledger_operation_id", 36))
            lease_owner = _required_string(payload, "lease_owner", 200)
            reason = _required_string(payload, "reason", 2000)
            await runtime.gateway.mark_ambiguous(
                ledger_operation_id,
                lease_owner=lease_owner,
                reason=reason,
            )
        except IdempotencyError as exc:
            return _error(exc.http_status, exc.code, "agent control ambiguity could not be committed")
        except (ValueError, TypeError) as exc:
            return _error(422, "AGENT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_IDEMPOTENCY_UNAVAILABLE",
                "canonical idempotency persistence is unavailable",
            )
        return JSONResponse(status_code=200, content={"status": "ambiguous"})

    @router.post("/approvals/read")
    async def read_approval(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            approval_id = UUID(_required_string(payload_or_error, "approval_id", 36))
            async with runtime.session_factory() as session:
                approval = await session.scalar(select(Approval).where(Approval.id == approval_id))
            if approval is None or approval.agent_run_id is None:
                return _error(404, "AGENT_CONTROL_APPROVAL_NOT_FOUND", "approval was not found")
        except (ValueError, TypeError) as exc:
            return _error(422, "AGENT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_APPROVAL_UNAVAILABLE",
                "canonical approval persistence is unavailable",
            )
        return JSONResponse(
            status_code=200,
            content={
                "approval_id": str(approval.id),
                "organization_id": str(approval.organization_id),
                "project_id": str(approval.project_id),
                "agent_run_id": str(approval.agent_run_id),
                "status": approval.status,
                "decision_payload": {
                    "reason": approval.reason,
                    "decided_by": str(approval.decided_by) if approval.decided_by else None,
                    "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
                    "task_id": str(approval.task_id) if approval.task_id else None,
                    "tool_key": approval.tool_key,
                },
            },
        )

    @router.post("/events/publish")
    async def publish_event(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        try:
            payload = payload_or_error
            organization_id = UUID(_required_string(payload, "organization_id", 36))
            project_id = UUID(_required_string(payload, "project_id", 36))
            agent_run_id = UUID(_required_string(payload, "agent_run_id", 36))
            event_type = _required_string(payload, "event_type", 128)
            canonical = _canonical_json_bytes(payload)
            event_id = uuid5(_EVENT_NAMESPACE, hashlib.sha256(canonical).hexdigest())
            event_payload = {
                "schema_version": 1,
                "project_id": str(project_id),
                "agent_run_id": str(agent_run_id),
                "thread_id": _required_string(payload, "thread_id", 255),
                "graph_key": _required_string(payload, "graph_key", 128),
                "graph_version": _required_string(payload, "graph_version", 100),
                "checkpoint_id": _optional_string(payload.get("checkpoint_id"), 512),
                "occurred_at": _required_string(payload, "occurred_at", 64),
                "payload": _required_object(payload, "payload"),
                "trace_id": _optional_string(payload.get("trace_id"), 128),
            }
            async with runtime.session_factory() as session:
                run = await session.scalar(
                    select(AgentRun).where(
                        AgentRun.id == agent_run_id,
                        AgentRun.organization_id == organization_id,
                        AgentRun.project_id == project_id,
                    )
                )
                if run is None or run.graph_version != event_payload["graph_version"]:
                    return _error(
                        409,
                        "AGENT_CONTROL_EVENT_SCOPE_MISMATCH",
                        "event does not match canonical AgentRun scope",
                    )
                statement = (
                    insert(OutboxEvent)
                    .values(
                        id=event_id,
                        organization_id=organization_id,
                        event_name=event_type,
                        aggregate_type="agent_run",
                        aggregate_id=agent_run_id,
                        schema_version=1,
                        payload_json=event_payload,
                        published_at=None,
                        publish_attempts=0,
                    )
                    .on_conflict_do_nothing(index_elements=[OutboxEvent.id])
                )
                await session.execute(statement)
                await session.commit()
        except (ValueError, TypeError) as exc:
            return _error(422, "AGENT_CONTROL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "AGENT_CONTROL_EVENT_UNAVAILABLE",
                "canonical outbox persistence is unavailable",
            )
        return JSONResponse(
            status_code=200,
            content={"status": "recorded", "event_id": str(event_id)},
        )

    return router


async def _authenticated_json(
    request: Request,
    secret: str,
) -> dict[str, Any] | JSONResponse:
    length_raw = request.headers.get("content-length")
    if length_raw is not None:
        try:
            length = int(length_raw)
        except ValueError:
            return _error(400, "AGENT_CONTROL_CONTENT_LENGTH_INVALID", "invalid content length")
        if length < 0 or length > _MAX_BODY_BYTES:
            return _error(413, "AGENT_CONTROL_REQUEST_TOO_LARGE", "request body is too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(413, "AGENT_CONTROL_REQUEST_TOO_LARGE", "request body is too large")
    auth_error = _verify_auth(request, body, secret)
    if auth_error is not None:
        return auth_error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(422, "AGENT_CONTROL_JSON_INVALID", str(exc))
    if not isinstance(payload, dict):
        return _error(422, "AGENT_CONTROL_OBJECT_REQUIRED", "request body must be an object")
    return dict(payload)


def _verify_auth(request: Request, body: bytes, secret: str) -> JSONResponse | None:
    service = request.headers.get(_SERVICE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(401, "AGENT_CONTROL_CALLER_FORBIDDEN", "internal authentication failed")
    try:
        timestamp = int(request.headers.get(_TIMESTAMP_HEADER, ""))
    except ValueError:
        return _error(401, "AGENT_CONTROL_TIMESTAMP_INVALID", "internal authentication failed")
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(401, "AGENT_CONTROL_TIMESTAMP_EXPIRED", "internal authentication failed")
    signature = request.headers.get(_SIGNATURE_HEADER)
    if signature is None or len(signature) != 64:
        return _error(401, "AGENT_CONTROL_SIGNATURE_INVALID", "internal authentication failed")
    body_hash = hashlib.sha256(body).hexdigest()
    message = (
        f"{service}\n{timestamp}\n{request.method.upper()}\n{request.url.path}\n{body_hash}"
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        return _error(401, "AGENT_CONTROL_SIGNATURE_INVALID", "internal authentication failed")
    return None


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _required_string(payload: dict[str, Any], key: str, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ValueError(f"AGENT_CONTROL_FIELD_INVALID:{key}")
    return value


def _required_hash(payload: dict[str, Any], key: str) -> str:
    value = _required_string(payload, key, 64).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"AGENT_CONTROL_HASH_INVALID:{key}")
    return value


def _optional_string(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
        raise ValueError("AGENT_CONTROL_OPTIONAL_STRING_INVALID")
    return value


def _required_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"AGENT_CONTROL_OBJECT_INVALID:{key}")
    return dict(value)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
