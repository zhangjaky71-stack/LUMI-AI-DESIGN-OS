from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .errors import AuthError, InvalidCredentials, PermissionDenied, RegistrationRejected, SessionInvalid, TokenInvalid
from .membership import MembershipService
from .notifications import AuthNotificationNotConfigured, AuthNotificationPort
from .principal import PrincipalResolver
from .schemas_v1 import (
    AcceptedResponse,
    ApiTokenCreateRequest,
    ApiTokenCreateResponse,
    InviteAcceptRequest,
    InviteCreateRequest,
    LoginRequest,
    LoginResponse,
    MemberRoleUpdateRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    VerifyEmailRequest,
)
from .service import AuthService

SESSION_COOKIE = "lumi_session"
CSRF_HEADER = "X-CSRF-Token"


def _request_id(request: Request) -> str:
    value = request.headers.get("x-request-id")
    return value if value else f"req-{id(request):x}"


def _trace_id(request: Request) -> str:
    return request.headers.get("traceparent", _request_id(request))


def _client_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _problem(status: int, code: str, title: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://errors.lumi.dev/auth/{code.lower().replace('_', '-')}",
            "title": title,
            "status": status,
            "code": code,
            "detail": title,
            "request_id": _request_id(request),
            "fields": {},
        },
    )


def create_auth_router(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    notifications: AuthNotificationPort,
    allowed_origins: frozenset[str],
    secure_cookie: bool = True,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

    @router.post("/register", response_model=AcceptedResponse, status_code=202, operation_id="registerLocalUser")
    async def register(payload: RegisterRequest, request: Request) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    service = AuthService(session)
                    result = await service.register_local(
                        email=payload.email,
                        password=payload.password,
                        display_name=payload.display_name,
                        organization_name=payload.organization_name,
                        organization_slug=payload.organization_slug,
                        client_key=_client_key(request),
                        request_id=_request_id(request),
                    )
                    await notifications.send_email_verification(
                        email=payload.email,
                        token=result.email_verification_token,
                    )
        except RegistrationRejected:
            # Deliberately indistinguishable from accepted registration to reduce account enumeration.
            return AcceptedResponse()
        except AuthNotificationNotConfigured:
            return _problem(503, "AUTH_NOTIFICATION_UNAVAILABLE", "Authentication email delivery is unavailable", request)
        except ValueError:
            return _problem(422, "INVALID_REGISTRATION", "Registration request is invalid", request)
        return AcceptedResponse()

    @router.post("/verify-email", response_model=AcceptedResponse, operation_id="verifyEmail")
    async def verify_email(payload: VerifyEmailRequest, request: Request) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    await AuthService(session).verify_email(payload.token)
        except TokenInvalid:
            return _problem(400, "TOKEN_INVALID_OR_EXPIRED", "Verification token is invalid or expired", request)
        return AcceptedResponse()

    @router.post("/login", response_model=LoginResponse, operation_id="loginLocalUser")
    async def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    result = await AuthService(session).login_local(
                        email=payload.email,
                        password=payload.password,
                        client_key=_client_key(request),
                        requested_organization_id=payload.organization_id,
                        user_agent=request.headers.get("user-agent"),
                        request_id=_request_id(request),
                    )
        except InvalidCredentials:
            return _problem(401, "INVALID_CREDENTIALS", "Invalid email or password", request)
        except AuthError:
            return _problem(401, "AUTHENTICATION_FAILED", "Authentication failed", request)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=result.session_token,
            expires=result.expires_at,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            path="/",
        )
        return LoginResponse(
            user_id=result.user_id,
            organization_id=result.organization_id,
            csrf_token=result.csrf_token,
            expires_at=result.expires_at,
        )

    @router.post("/logout", response_model=AcceptedResponse, operation_id="logoutUser")
    async def logout(
        request: Request,
        response: Response,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> AcceptedResponse | JSONResponse:
        session_token = request.cookies.get(SESSION_COOKIE)
        if not session_token:
            return _problem(401, "SESSION_INVALID", "Session is invalid", request)
        try:
            async with session_factory() as session:
                async with session.begin():
                    await AuthService(session).logout(
                        session_token=session_token,
                        csrf_token=x_csrf_token,
                        origin=request.headers.get("origin"),
                        allowed_origins=allowed_origins,
                        request_id=_request_id(request),
                    )
        except SessionInvalid:
            return _problem(401, "SESSION_INVALID", "Session is invalid", request)
        response.delete_cookie(SESSION_COOKIE, path="/", secure=secure_cookie, httponly=True, samesite="lax")
        return AcceptedResponse()

    @router.post("/password-reset", response_model=AcceptedResponse, status_code=202, operation_id="requestPasswordReset")
    async def password_reset(payload: PasswordResetRequest, request: Request) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    token = await AuthService(session).request_password_reset(
                        email=payload.email,
                        client_key=_client_key(request),
                    )
                    if token is not None:
                        await notifications.send_password_reset(email=payload.email, token=token)
        except AuthNotificationNotConfigured:
            return _problem(503, "AUTH_NOTIFICATION_UNAVAILABLE", "Authentication email delivery is unavailable", request)
        except ValueError:
            # Keep enumeration-safe outward semantics for malformed/not-found lookup details.
            return AcceptedResponse()
        return AcceptedResponse()

    @router.post("/password-reset/confirm", response_model=AcceptedResponse, operation_id="confirmPasswordReset")
    async def password_reset_confirm(
        payload: PasswordResetConfirmRequest,
        request: Request,
    ) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    await AuthService(session).reset_password(
                        plaintext_token=payload.token,
                        new_password=payload.new_password,
                    )
        except TokenInvalid:
            return _problem(400, "TOKEN_INVALID_OR_EXPIRED", "Reset token is invalid or expired", request)
        except ValueError:
            return _problem(422, "INVALID_PASSWORD", "New password does not meet requirements", request)
        return AcceptedResponse()

    async def _session_principal(
        session: AsyncSession,
        request: Request,
        requested_organization_id: UUID | None,
    ) -> tuple[Any, str] | JSONResponse:
        session_token = request.cookies.get(SESSION_COOKIE)
        if not session_token:
            return _problem(401, "SESSION_INVALID", "Session is invalid", request)
        try:
            principal = await PrincipalResolver(session).from_session(
                plaintext_session_token=session_token,
                request_id=_request_id(request),
                trace_id=_trace_id(request),
                now=datetime.now(UTC),
                requested_organization_id=requested_organization_id,
            )
        except SessionInvalid:
            return _problem(401, "SESSION_INVALID", "Session is invalid", request)
        return principal, session_token

    def _require_csrf(
        *,
        csrf_token_hash: str,
        session_token_hash: str,
        user_id: str,
        organization_id: str,
        request: Request,
        csrf_token: str | None,
    ) -> JSONResponse | None:
        from lumi_auth import SessionRecord, validate_csrf
        from lumi_auth.tokens import hash_token

        now = datetime.now(UTC)
        record = SessionRecord(
            session_token_hash=session_token_hash,
            csrf_token_hash=csrf_token_hash,
            user_id=user_id,
            organization_id=organization_id,
            created_at=now,
            expires_at=now.replace(year=now.year + 1),
        )
        try:
            validate_csrf(
                record,
                csrf_token=csrf_token,
                origin=request.headers.get("origin"),
                allowed_origins=allowed_origins,
            )
        except PermissionError:
            return _problem(403, "CSRF_INVALID", "CSRF validation failed", request)
        _ = hash_token  # keep validation implementation centralized in lumi_auth
        return None

    @router.post(
        "/organizations/{organization_id}/invites",
        response_model=AcceptedResponse,
        status_code=202,
        operation_id="createOrganizationInvite",
    )
    async def create_invite(
        organization_id: UUID,
        payload: InviteCreateRequest,
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    resolved = await _session_principal(session, request, organization_id)
                    if isinstance(resolved, JSONResponse):
                        return resolved
                    principal, session_token = resolved
                    csrf_problem = _require_csrf(
                        csrf_token_hash=principal.csrf_token_hash,
                        session_token_hash=session_token,
                        user_id=principal.context.actor_id,
                        organization_id=principal.context.organization_id,
                        request=request,
                        csrf_token=x_csrf_token,
                    )
                    if csrf_problem is not None:
                        return csrf_problem
                    token = await AuthService(session).create_invite(
                        actor_id=UUID(principal.context.actor_id),
                        organization_id=organization_id,
                        email=payload.email,
                        role=payload.role,
                        client_key=_client_key(request),
                    )
                    await notifications.send_organization_invite(
                        email=payload.email,
                        organization_id=str(organization_id),
                        token=token,
                    )
        except PermissionDenied:
            return _problem(403, "PERMISSION_DENIED", "Permission denied", request)
        except AuthNotificationNotConfigured:
            return _problem(503, "AUTH_NOTIFICATION_UNAVAILABLE", "Authentication email delivery is unavailable", request)
        return AcceptedResponse()

    @router.post("/invites/accept", response_model=AcceptedResponse, operation_id="acceptOrganizationInvite")
    async def accept_invite(
        payload: InviteAcceptRequest,
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    resolved = await _session_principal(session, request, None)
                    if isinstance(resolved, JSONResponse):
                        return resolved
                    principal, session_token = resolved
                    csrf_problem = _require_csrf(
                        csrf_token_hash=principal.csrf_token_hash,
                        session_token_hash=session_token,
                        user_id=principal.context.actor_id,
                        organization_id=principal.context.organization_id,
                        request=request,
                        csrf_token=x_csrf_token,
                    )
                    if csrf_problem is not None:
                        return csrf_problem
                    await AuthService(session).accept_invite(
                        actor_id=UUID(principal.context.actor_id),
                        plaintext_token=payload.token,
                    )
        except TokenInvalid:
            return _problem(400, "TOKEN_INVALID_OR_EXPIRED", "Invite is invalid or expired", request)
        return AcceptedResponse()

    @router.post(
        "/organizations/{organization_id}/api-tokens",
        response_model=ApiTokenCreateResponse,
        status_code=201,
        operation_id="createApiToken",
    )
    async def create_api_token(
        organization_id: UUID,
        payload: ApiTokenCreateRequest,
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> ApiTokenCreateResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    resolved = await _session_principal(session, request, organization_id)
                    if isinstance(resolved, JSONResponse):
                        return resolved
                    principal, session_token = resolved
                    csrf_problem = _require_csrf(
                        csrf_token_hash=principal.csrf_token_hash,
                        session_token_hash=session_token,
                        user_id=principal.context.actor_id,
                        organization_id=principal.context.organization_id,
                        request=request,
                        csrf_token=x_csrf_token,
                    )
                    if csrf_problem is not None:
                        return csrf_problem
                    result = await AuthService(session).create_api_token(
                        actor_id=UUID(principal.context.actor_id),
                        organization_id=organization_id,
                        name=payload.name,
                        scopes=frozenset(payload.scopes),
                        expires_at=payload.expires_at,
                    )
        except PermissionDenied:
            return _problem(403, "PERMISSION_DENIED", "Permission denied", request)
        return ApiTokenCreateResponse(
            token_id=result.token_id,
            token=result.plaintext,
            prefix=result.prefix,
        )

    @router.delete(
        "/organizations/{organization_id}/api-tokens/{token_id}",
        response_model=AcceptedResponse,
        operation_id="revokeApiToken",
    )
    async def revoke_api_token(
        organization_id: UUID,
        token_id: UUID,
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    resolved = await _session_principal(session, request, organization_id)
                    if isinstance(resolved, JSONResponse):
                        return resolved
                    principal, session_token = resolved
                    csrf_problem = _require_csrf(
                        csrf_token_hash=principal.csrf_token_hash,
                        session_token_hash=session_token,
                        user_id=principal.context.actor_id,
                        organization_id=principal.context.organization_id,
                        request=request,
                        csrf_token=x_csrf_token,
                    )
                    if csrf_problem is not None:
                        return csrf_problem
                    await PrincipalResolver(session).revoke_api_token(
                        actor_id=UUID(principal.context.actor_id),
                        organization_id=organization_id,
                        token_id=token_id,
                        now=datetime.now(UTC),
                    )
        except PermissionDenied:
            return _problem(403, "PERMISSION_DENIED", "Permission denied", request)
        return AcceptedResponse()

    @router.patch(
        "/organizations/{organization_id}/members/{user_id}",
        response_model=AcceptedResponse,
        operation_id="changeOrganizationMemberRole",
    )
    async def change_member_role(
        organization_id: UUID,
        user_id: UUID,
        payload: MemberRoleUpdateRequest,
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    resolved = await _session_principal(session, request, organization_id)
                    if isinstance(resolved, JSONResponse):
                        return resolved
                    principal, session_token = resolved
                    csrf_problem = _require_csrf(
                        csrf_token_hash=principal.csrf_token_hash,
                        session_token_hash=session_token,
                        user_id=principal.context.actor_id,
                        organization_id=principal.context.organization_id,
                        request=request,
                        csrf_token=x_csrf_token,
                    )
                    if csrf_problem is not None:
                        return csrf_problem
                    await MembershipService(session).change_role(
                        organization_id=organization_id,
                        actor_id=UUID(principal.context.actor_id),
                        target_user_id=user_id,
                        new_role=payload.role,
                    )
        except PermissionDenied:
            return _problem(403, "PERMISSION_DENIED", "Permission denied", request)
        except ValueError as exc:
            code = "LAST_OWNER_REQUIRED" if "LAST_OWNER_REQUIRED" in str(exc) else "INVALID_ROLE"
            return _problem(409 if code == "LAST_OWNER_REQUIRED" else 422, code, "Membership change rejected", request)
        return AcceptedResponse()

    @router.delete(
        "/organizations/{organization_id}/members/{user_id}",
        response_model=AcceptedResponse,
        operation_id="removeOrganizationMember",
    )
    async def remove_member(
        organization_id: UUID,
        user_id: UUID,
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    ) -> AcceptedResponse | JSONResponse:
        try:
            async with session_factory() as session:
                async with session.begin():
                    resolved = await _session_principal(session, request, organization_id)
                    if isinstance(resolved, JSONResponse):
                        return resolved
                    principal, session_token = resolved
                    csrf_problem = _require_csrf(
                        csrf_token_hash=principal.csrf_token_hash,
                        session_token_hash=session_token,
                        user_id=principal.context.actor_id,
                        organization_id=principal.context.organization_id,
                        request=request,
                        csrf_token=x_csrf_token,
                    )
                    if csrf_problem is not None:
                        return csrf_problem
                    await MembershipService(session).remove_member(
                        organization_id=organization_id,
                        actor_id=UUID(principal.context.actor_id),
                        target_user_id=user_id,
                    )
        except PermissionDenied:
            return _problem(403, "PERMISSION_DENIED", "Permission denied", request)
        except ValueError:
            return _problem(409, "LAST_OWNER_REQUIRED", "Membership change rejected", request)
        return AcceptedResponse()

    return router
