from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request
from lumi_auth import SessionRecord, validate_csrf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.api.v1.context import RequestContext
from lumi_api.api.v1.errors import ApiProblem
from lumi_api.auth.errors import AuthError, PermissionDenied, SessionInvalid
from lumi_api.auth.principal import PrincipalResolver
from lumi_api.persistence.models import Session

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "missing-request-id"))


def _trace_id(request: Request) -> str:
    supplied = request.headers.get("X-Trace-Id", "").strip()
    return supplied if 1 <= len(supplied) <= 128 else _request_id(request)


def _organization_id(request: Request) -> UUID:
    value = request.headers.get("X-Lumi-Organization-Id", "").strip()
    if not value:
        raise ApiProblem(
            status=400,
            code="ORGANIZATION_REQUIRED",
            title="Organization required",
            detail="X-Lumi-Organization-Id is required.",
        )
    try:
        return UUID(value)
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="INVALID_ORGANIZATION_ID",
            title="Invalid organization",
        ) from exc


def _bearer_token(request: Request) -> str | None:
    value = request.headers.get("Authorization", "").strip()
    if not value:
        return None
    scheme, separator, credential = value.partition(" ")
    if not separator or scheme.lower() != "bearer" or not credential.strip():
        raise ApiProblem(status=401, code="AUTH_REQUIRED", title="Authentication required")
    return credential.strip()


def _allowed_origins(request: Request) -> frozenset[str]:
    value = getattr(request.app.state, "project_allowed_origins", frozenset())
    return frozenset(str(item) for item in value)


async def _validate_browser_csrf(
    session: AsyncSession,
    *,
    session_id: UUID,
    request: Request,
    now: datetime,
) -> None:
    row = await session.scalar(select(Session).where(Session.id == session_id))
    if row is None or row.csrf_token_hash is None:
        raise ApiProblem(status=401, code="SESSION_INVALID", title="Session invalid")
    record = SessionRecord(
        session_token_hash=row.token_hash,
        csrf_token_hash=row.csrf_token_hash,
        user_id=str(row.user_id),
        organization_id=str(row.organization_id) if row.organization_id else None,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_seen_at=row.last_seen_at,
        revoked_at=row.revoked_at,
        user_agent_hash=row.user_agent_hash,
    )
    try:
        validate_csrf(
            record,
            csrf_token=request.headers.get("X-CSRF-Token"),
            origin=request.headers.get("Origin"),
            allowed_origins=_allowed_origins(request),
        )
    except PermissionError as exc:
        raise ApiProblem(
            status=403,
            code="CSRF_VALIDATION_FAILED",
            title="CSRF validation failed",
        ) from exc


async def get_secure_project_context(request: Request) -> RequestContext:
    organization_id = _organization_id(request)
    factory = getattr(request.app.state, "project_session_factory", None)
    if not isinstance(factory, async_sessionmaker):
        raise ApiProblem(
            status=503,
            code="PROJECT_RUNTIME_NOT_READY",
            title="Project runtime not ready",
        )

    required_permission = "project.read" if request.method in _SAFE_METHODS else "project.write"
    now = datetime.now(UTC)
    async with factory() as session:
        async with session.begin():
            resolver = PrincipalResolver(session)
            bearer = _bearer_token(request)
            if bearer is not None:
                try:
                    principal = await resolver.from_api_token(
                        plaintext_token=bearer,
                        required_scope=required_permission,
                        now=now,
                    )
                except (PermissionDenied, AuthError) as exc:
                    raise ApiProblem(
                        status=403,
                        code="PERMISSION_DENIED",
                        title="Permission denied",
                    ) from exc
                if principal.organization_id != organization_id:
                    raise ApiProblem(
                        status=404,
                        code="PROJECT_NOT_FOUND_OR_FORBIDDEN",
                        title="Resource not found",
                    )
                return RequestContext(
                    organization_id=organization_id,
                    request_id=_request_id(request),
                    actor_id=principal.created_by,
                    actor_type="api_token",
                    permissions=principal.scopes,
                    trace_id=_trace_id(request),
                    api_token_id=principal.token_id,
                )

            plaintext_session = request.cookies.get("lumi_session")
            if not plaintext_session:
                raise ApiProblem(
                    status=401,
                    code="AUTH_REQUIRED",
                    title="Authentication required",
                )
            try:
                principal = await resolver.from_session(
                    plaintext_session_token=plaintext_session,
                    request_id=_request_id(request),
                    trace_id=_trace_id(request),
                    now=now,
                    requested_organization_id=organization_id,
                )
            except SessionInvalid as exc:
                raise ApiProblem(
                    status=401,
                    code="SESSION_INVALID",
                    title="Session invalid",
                ) from exc

            if required_permission not in principal.context.permissions:
                raise ApiProblem(
                    status=403,
                    code="PERMISSION_DENIED",
                    title="Permission denied",
                )
            if request.method not in _SAFE_METHODS:
                await _validate_browser_csrf(
                    session,
                    session_id=principal.session_id,
                    request=request,
                    now=now,
                )
            return RequestContext(
                organization_id=organization_id,
                request_id=_request_id(request),
                actor_id=UUID(principal.context.actor_id),
                actor_type="user",
                permissions=frozenset(principal.context.permissions),
                trace_id=principal.context.trace_id,
            )
