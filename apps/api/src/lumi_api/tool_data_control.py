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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.persistence.models import Project, Task

_MAX_BODY_BYTES = 512 * 1024
_MAX_SKEW_SECONDS = 90
_ALLOWED_CALLERS = frozenset({"tool-gateway"})
_SERVICE_HEADER = "X-Lumi-Service"
_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_SIGNATURE_HEADER = "X-Lumi-Signature"
_PROJECT_SUMMARY_QUERY = "project.summary"


class ToolDataStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def query_project(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        query: str,
    ) -> dict[str, Any]:
        if query != _PROJECT_SUMMARY_QUERY:
            raise ValueError("TOOL_DATA_PROJECT_QUERY_UNSUPPORTED")
        async with self._session_factory() as session:
            task = await session.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.organization_id == organization_id,
                    Task.agent_run_id == agent_run_id,
                )
            )
            if task is None:
                raise KeyError("TOOL_DATA_TASK_NOT_FOUND_OR_FORBIDDEN")
            project = await session.scalar(
                select(Project).where(
                    Project.id == task.project_id,
                    Project.organization_id == organization_id,
                    Project.deleted_at.is_(None),
                )
            )
            if project is None:
                raise KeyError("TOOL_DATA_PROJECT_NOT_FOUND_OR_FORBIDDEN")
            return {
                "project_id": str(project.id),
                "name": project.name,
                "status": project.status,
                "summary": dict(project.brief_json),
            }


@dataclass(frozen=True, slots=True)
class ToolDataControlRuntime:
    store: ToolDataStore
    auth_secret: str


def build_tool_data_control_runtime(
    session_factory: async_sessionmaker[AsyncSession],
) -> ToolDataControlRuntime:
    secret = os.getenv("LUMI_TOOL_DATA_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_TOOL_DATA_AUTH_SECRET_REQUIRED")
    return ToolDataControlRuntime(
        store=ToolDataStore(session_factory),
        auth_secret=secret,
    )


def create_tool_data_control_router(runtime: ToolDataControlRuntime) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/tool-data", tags=["internal-tool-data"])

    @router.post("/project/query")
    async def project_query(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        try:
            result = await runtime.store.query_project(
                organization_id=UUID(_required_string(payload, "organization_id", 36)),
                agent_run_id=UUID(_required_string(payload, "agent_run_id", 36)),
                task_id=UUID(_required_string(payload, "task_id", 36)),
                query=_required_string(payload, "query", 128),
            )
        except ValueError as exc:
            return _error(422, "TOOL_DATA_QUERY_INVALID", str(exc))
        except KeyError as exc:
            return _error(404, "TOOL_DATA_NOT_FOUND_OR_FORBIDDEN", str(exc))
        except Exception:
            return _error(
                503,
                "TOOL_DATA_CONTROL_UNAVAILABLE",
                "canonical Tool Data control plane is unavailable",
            )
        return JSONResponse(status_code=200, content=result)

    return router


async def _authenticated_json(request: Request, secret: str) -> dict[str, Any] | JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return _error(400, "TOOL_DATA_CONTENT_LENGTH_INVALID", "invalid content length")
        if parsed_length < 0 or parsed_length > _MAX_BODY_BYTES:
            return _error(413, "TOOL_DATA_REQUEST_TOO_LARGE", "request body is too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(413, "TOOL_DATA_REQUEST_TOO_LARGE", "request body is too large")
    auth_error = _verify_auth(request, body, secret)
    if auth_error is not None:
        return auth_error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(422, "TOOL_DATA_JSON_INVALID", str(exc))
    if not isinstance(payload, dict):
        return _error(422, "TOOL_DATA_OBJECT_REQUIRED", "request body must be an object")
    return dict(payload)


def _verify_auth(request: Request, body: bytes, secret: str) -> JSONResponse | None:
    service = request.headers.get(_SERVICE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(401, "TOOL_DATA_CALLER_FORBIDDEN", "internal authentication failed")
    try:
        timestamp = int(request.headers.get(_TIMESTAMP_HEADER, ""))
    except ValueError:
        return _error(401, "TOOL_DATA_TIMESTAMP_INVALID", "internal authentication failed")
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(401, "TOOL_DATA_TIMESTAMP_EXPIRED", "internal authentication failed")
    signature = request.headers.get(_SIGNATURE_HEADER)
    if signature is None or len(signature) != 64:
        return _error(401, "TOOL_DATA_SIGNATURE_INVALID", "internal authentication failed")
    body_hash = hashlib.sha256(body).hexdigest()
    message = (
        f"{service}\n{timestamp}\n{request.method.upper()}\n{request.url.path}\n{body_hash}"
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        return _error(401, "TOOL_DATA_SIGNATURE_INVALID", "internal authentication failed")
    return None


def _required_string(payload: dict[str, Any], key: str, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ValueError(f"TOOL_DATA_FIELD_INVALID:{key}")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
