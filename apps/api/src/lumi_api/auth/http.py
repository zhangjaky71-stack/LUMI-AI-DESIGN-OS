from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .models import Principal
from .security import validate_csrf
from .service import AuthService, InvalidCredentials


@dataclass(frozen=True, slots=True)
class SessionCookiePolicy:
    name: str = "lumi_session"
    csrf_cookie_name: str = "lumi_csrf"
    path: str = "/"
    httponly: bool = True
    secure: bool = True
    samesite: str = "lax"

    @classmethod
    def for_environment(cls, environment: str) -> SessionCookiePolicy:
        return cls(secure=environment.casefold() not in {"local", "development", "test"})


@dataclass(frozen=True, slots=True)
class HttpAuthInput:
    method: str
    organization_id: UUID
    origin: str | None
    authorization: str | None
    session_cookie: str | None
    csrf_cookie: str | None
    csrf_header: str | None


def authenticate_http_request(
    request: HttpAuthInput,
    *,
    auth_service: AuthService,
    now: datetime,
    allowed_origins: frozenset[str],
) -> Principal:
    if request.authorization:
        scheme, _, credential = request.authorization.partition(" ")
        if scheme.casefold() != "bearer" or not credential:
            raise InvalidCredentials("AUTHORIZATION_INVALID")
        principal = auth_service.authenticate_api_token(credential, now=now)
        if principal.organization_id != request.organization_id:
            raise InvalidCredentials("TENANT_RESOURCE_NOT_FOUND")
        return principal

    if not request.session_cookie:
        raise InvalidCredentials("AUTHENTICATION_REQUIRED")
    validate_csrf(
        method=request.method,
        origin=request.origin,
        allowed_origins=allowed_origins,
        csrf_cookie=request.csrf_cookie,
        csrf_header=request.csrf_header,
    )
    return auth_service.principal_for_session(
        request.session_cookie,
        organization_id=request.organization_id,
        now=now,
    )
