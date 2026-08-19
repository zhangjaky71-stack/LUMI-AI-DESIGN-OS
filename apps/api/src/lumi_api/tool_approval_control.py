from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from lumi_domain import new_uuid7
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.api.v1.context import RequestContext, get_request_context
from lumi_api.persistence.models import Approval, Task

_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_SKEW_SECONDS = 90
_ALLOWED_CALLERS = frozenset({"tool-gateway"})
_SERVICE_HEADER = "X-Lumi-Service"
_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_SIGNATURE_HEADER = "X-Lumi-Signature"


@dataclass(frozen=True, slots=True)
class ToolApprovalScope:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID
    tool_key: str
    request_hash: str


@dataclass(frozen=True, slots=True)
class ToolApprovalResolution:
    decision: Literal["REQUIRED", "APPROVED", "DENIED"]
    approval_id: UUID
    reason_code: str


class ToolApprovalStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        tool_key: str,
        request_hash: str,
        approval_id: UUID | None,
    ) -> ToolApprovalResolution:
        async with self._session_factory() as session:
            task = await session.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.organization_id == organization_id,
                    Task.agent_run_id == agent_run_id,
                )
            )
            if task is None:
                raise ValueError("TOOL_APPROVAL_TASK_NOT_FOUND_OR_FORBIDDEN")
            scope = ToolApprovalScope(
                organization_id=organization_id,
                project_id=task.project_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
                tool_key=tool_key,
                request_hash=request_hash,
            )

            if approval_id is not None:
                approval = await session.scalar(
                    select(Approval).where(
                        Approval.id == approval_id,
                        Approval.organization_id == scope.organization_id,
                        Approval.project_id == scope.project_id,
                        Approval.agent_run_id == scope.agent_run_id,
                        Approval.task_id == scope.task_id,
                        Approval.tool_key == scope.tool_key,
                        Approval.tool_request_hash == scope.request_hash,
                    )
                )
                if approval is None:
                    return ToolApprovalResolution(
                        decision="DENIED",
                        approval_id=approval_id,
                        reason_code="TOOL_APPROVAL_SCOPE_MISMATCH",
                    )
                return _resolution(approval)

            existing = await session.scalar(_scope_query(scope))
            if existing is None:
                statement = (
                    insert(Approval)
                    .values(
                        id=new_uuid7(),
                        organization_id=scope.organization_id,
                        project_id=scope.project_id,
                        artifact_version_id=None,
                        agent_run_id=scope.agent_run_id,
                        task_id=scope.task_id,
                        tool_key=scope.tool_key,
                        tool_request_hash=scope.request_hash,
                        requested_by=None,
                        decided_by=None,
                        status="pending",
                        reason=None,
                        decided_at=None,
                        version=1,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            Approval.organization_id,
                            Approval.task_id,
                            Approval.tool_key,
                            Approval.tool_request_hash,
                        ],
                        index_where=Approval.tool_key.is_not(None),
                    )
                    .returning(Approval.id)
                )
                await session.execute(statement)
                await session.commit()
                existing = await session.scalar(_scope_query(scope))
            if existing is None:
                raise RuntimeError("TOOL_APPROVAL_PERSISTENCE_FAILED")
            return _resolution(existing)


@dataclass(frozen=True, slots=True)
class ToolApprovalControlRuntime:
    store: ToolApprovalStore
    auth_secret: str


def build_tool_approval_control_runtime(
    session_factory: async_sessionmaker[AsyncSession],
) -> ToolApprovalControlRuntime:
    secret = os.getenv("LUMI_TOOL_APPROVAL_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_TOOL_APPROVAL_AUTH_SECRET_REQUIRED")
    return ToolApprovalControlRuntime(
        store=ToolApprovalStore(session_factory),
        auth_secret=secret,
    )


def create_tool_approval_control_router(runtime: ToolApprovalControlRuntime) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/tool-approval", tags=["internal-tool-approval"])

    @router.post("/resolve")
    async def resolve(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        try:
            organization_id = UUID(_required_string(payload, "organization_id", 36))
            agent_run_id = UUID(_required_string(payload, "agent_run_id", 36))
            task_id = UUID(_required_string(payload, "task_id", 36))
            tool_key = _required_string(payload, "tool_key", 320)
            purpose = _required_string(payload, "purpose", 1000)
            arguments = payload.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("TOOL_APPROVAL_ARGUMENTS_INVALID")
            approval_raw = payload.get("approval_id")
            approval_id = (
                UUID(approval_raw)
                if isinstance(approval_raw, str) and approval_raw
                else None
            )
            request_hash = _request_hash(
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
                tool_key=tool_key,
                purpose=purpose,
                arguments=arguments,
            )
            result = await runtime.store.resolve(
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
                tool_key=tool_key,
                request_hash=request_hash,
                approval_id=approval_id,
            )
        except ValueError as exc:
            return _error(422, "TOOL_APPROVAL_REQUEST_INVALID", str(exc))
        except Exception:
            return _error(
                503,
                "TOOL_APPROVAL_PERSISTENCE_UNAVAILABLE",
                "canonical tool approval persistence is unavailable",
            )
        return JSONResponse(
            status_code=200,
            content={
                "decision": result.decision,
                "approval_id": str(result.approval_id),
                "reason_code": result.reason_code,
                "request_hash": request_hash,
            },
        )

    return router


class ToolApprovalDecisionBody(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reason: str | None = Field(default=None, max_length=2000)


def create_tool_approval_public_router(
    session_factory: async_sessionmaker[AsyncSession],
) -> APIRouter:
    router = APIRouter(prefix="/projects/{project_id}/tool-approvals", tags=["tool-approvals"])

    @router.get("/{approval_id}")
    async def get_tool_approval(
        project_id: UUID,
        approval_id: UUID,
        context: RequestContext = Depends(get_request_context),
    ) -> JSONResponse:
        async with session_factory() as session:
            approval = await session.scalar(
                select(Approval).where(
                    Approval.id == approval_id,
                    Approval.organization_id == context.organization_id,
                    Approval.project_id == project_id,
                    Approval.tool_key.is_not(None),
                )
            )
            if approval is None:
                return _error(
                    404,
                    "TOOL_APPROVAL_NOT_FOUND",
                    "tool approval was not found",
                )
            return JSONResponse(status_code=200, content=_public_payload(approval))

    @router.post("/{approval_id}:decide")
    async def decide_tool_approval(
        project_id: UUID,
        approval_id: UUID,
        body: ToolApprovalDecisionBody,
        context: RequestContext = Depends(get_request_context),
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> JSONResponse:
        if "artifact.approve" not in context.permissions:
            return _error(
                403,
                "TOOL_APPROVAL_PERMISSION_DENIED",
                "artifact.approve permission is required",
            )
        if not idempotency_key.strip() or len(idempotency_key) > 512:
            return _error(
                422,
                "TOOL_APPROVAL_IDEMPOTENCY_KEY_INVALID",
                "invalid idempotency key",
            )
        async with session_factory() as session:
            async with session.begin():
                approval = await session.scalar(
                    select(Approval)
                    .where(
                        Approval.id == approval_id,
                        Approval.organization_id == context.organization_id,
                        Approval.project_id == project_id,
                        Approval.tool_key.is_not(None),
                    )
                    .with_for_update()
                )
                if approval is None:
                    return _error(
                        404,
                        "TOOL_APPROVAL_NOT_FOUND",
                        "tool approval was not found",
                    )
                desired = "approved" if body.decision == "APPROVE" else "rejected"
                current = approval.status.strip().lower()
                if current == desired:
                    return JSONResponse(
                        status_code=200,
                        content=_public_payload(approval),
                    )
                if current != "pending":
                    return _error(
                        409,
                        "TOOL_APPROVAL_ALREADY_RESOLVED",
                        "tool approval is no longer pending",
                    )
                approval.status = desired
                approval.decided_by = context.actor_id
                approval.decided_at = datetime.now(UTC)
                approval.reason = (
                    body.reason.strip()
                    if body.reason and body.reason.strip()
                    else None
                )
                approval.version += 1
            await session.refresh(approval)
            return JSONResponse(status_code=200, content=_public_payload(approval))

    return router


def _scope_query(scope: ToolApprovalScope):
    return select(Approval).where(
        Approval.organization_id == scope.organization_id,
        Approval.project_id == scope.project_id,
        Approval.agent_run_id == scope.agent_run_id,
        Approval.task_id == scope.task_id,
        Approval.tool_key == scope.tool_key,
        Approval.tool_request_hash == scope.request_hash,
    )


def _resolution(approval: Approval) -> ToolApprovalResolution:
    status = approval.status.strip().lower()
    if status == "approved":
        return ToolApprovalResolution("APPROVED", approval.id, "TOOL_APPROVAL_APPROVED")
    if status == "pending":
        return ToolApprovalResolution("REQUIRED", approval.id, "TOOL_APPROVAL_REQUIRED")
    return ToolApprovalResolution("DENIED", approval.id, f"TOOL_APPROVAL_{status.upper()}")


def _public_payload(approval: Approval) -> dict[str, Any]:
    return {
        "approval_id": str(approval.id),
        "project_id": str(approval.project_id),
        "agent_run_id": str(approval.agent_run_id) if approval.agent_run_id else None,
        "task_id": str(approval.task_id) if approval.task_id else None,
        "tool_key": approval.tool_key,
        "status": approval.status,
        "reason": approval.reason,
        "decided_by": str(approval.decided_by) if approval.decided_by else None,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
    }


def _request_hash(
    *,
    organization_id: UUID,
    agent_run_id: UUID,
    task_id: UUID,
    tool_key: str,
    purpose: str,
    arguments: dict[str, Any],
) -> str:
    payload = {
        "organization_id": str(organization_id),
        "agent_run_id": str(agent_run_id),
        "task_id": str(task_id),
        "tool_key": tool_key,
        "purpose": purpose,
        "arguments": arguments,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _authenticated_json(
    request: Request,
    secret: str,
) -> dict[str, Any] | JSONResponse:
    length_raw = request.headers.get("content-length")
    if length_raw is not None:
        try:
            length = int(length_raw)
        except ValueError:
            return _error(
                400,
                "TOOL_APPROVAL_CONTENT_LENGTH_INVALID",
                "invalid content length",
            )
        if length < 0 or length > _MAX_BODY_BYTES:
            return _error(
                413,
                "TOOL_APPROVAL_REQUEST_TOO_LARGE",
                "request body is too large",
            )
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(
            413,
            "TOOL_APPROVAL_REQUEST_TOO_LARGE",
            "request body is too large",
        )
    auth_error = _verify_auth(request, body, secret)
    if auth_error is not None:
        return auth_error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(422, "TOOL_APPROVAL_JSON_INVALID", str(exc))
    if not isinstance(payload, dict):
        return _error(
            422,
            "TOOL_APPROVAL_OBJECT_REQUIRED",
            "request body must be an object",
        )
    return dict(payload)


def _verify_auth(request: Request, body: bytes, secret: str) -> JSONResponse | None:
    service = request.headers.get(_SERVICE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(
            401,
            "TOOL_APPROVAL_CALLER_FORBIDDEN",
            "internal authentication failed",
        )
    try:
        timestamp = int(request.headers.get(_TIMESTAMP_HEADER, ""))
    except ValueError:
        return _error(
            401,
            "TOOL_APPROVAL_TIMESTAMP_INVALID",
            "internal authentication failed",
        )
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(
            401,
            "TOOL_APPROVAL_TIMESTAMP_EXPIRED",
            "internal authentication failed",
        )
    signature = request.headers.get(_SIGNATURE_HEADER)
    if signature is None or len(signature) != 64:
        return _error(
            401,
            "TOOL_APPROVAL_SIGNATURE_INVALID",
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
            "TOOL_APPROVAL_SIGNATURE_INVALID",
            "internal authentication failed",
        )
    return None


def _required_string(payload: dict[str, Any], key: str, max_length: int) -> str:
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or "\x00" in value
    ):
        raise ValueError(f"TOOL_APPROVAL_FIELD_INVALID:{key}")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
