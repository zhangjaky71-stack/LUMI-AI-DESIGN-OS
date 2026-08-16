from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from lumi_api.auth import (
    AuthFlowError,
    HttpAuthInput,
    InvalidCredentials,
    authenticate_http_request,
    hash_secret,
    validate_csrf,
)

from .auth_dependencies import AuthHttpSettingsDependency, AuthServiceDependency
from .auth_schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    PrincipalResponse,
    RegisterRequest,
    UserResponse,
)
from .errors import ApiProblem
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    auth: AuthServiceDependency,
) -> UserResponse:
    try:
        user = auth.register(
            email=payload.email,
            display_name=payload.display_name,
            password=payload.password,
            now=_now(),
        )
    except (ValueError, AuthFlowError) as exc:
        code = str(exc)
        raise ApiProblem(
            status=409 if code == "EMAIL_UNAVAILABLE" else 422,
            code=code.casefold(),
            title="Registration failed",
            detail="The registration request could not be completed.",
        ) from exc
    return UserResponse(id=user.id, email=user.email, display_name=user.display_name)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDependency,
    settings: AuthHttpSettingsDependency,
) -> LoginResponse:
    user_agent = request.headers.get("User-Agent")
    try:
        grant = auth.login(
            email=payload.email,
            password=payload.password,
            now=_now(),
            user_agent_hash=hash_secret(user_agent) if user_agent else None,
        )
    except InvalidCredentials as exc:
        raise ApiProblem(
            status=401,
            code="invalid_credentials",
            title="Authentication failed",
            detail="The supplied credentials are invalid.",
        ) from exc
    except ValueError as exc:
        if str(exc) == "RATE_LIMITED":
            raise ApiProblem(
                status=429,
                code="auth_rate_limited",
                title="Too many authentication attempts",
                detail="Try again later.",
            ) from exc
        raise

    policy = settings.cookie_policy
    response.set_cookie(
        key=policy.name,
        value=grant.session_secret,
        httponly=True,
        secure=policy.secure,
        samesite="lax",
        path=policy.path,
    )
    response.set_cookie(
        key=policy.csrf_cookie_name,
        value=grant.csrf_token,
        httponly=False,
        secure=policy.secure,
        samesite="lax",
        path=policy.path,
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user_id=grant.session.user_id)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    auth: AuthServiceDependency,
    settings: AuthHttpSettingsDependency,
) -> LogoutResponse:
    policy = settings.cookie_policy
    session_secret = request.cookies.get(policy.name)
    try:
        validate_csrf(
            method="POST",
            origin=request.headers.get("Origin"),
            allowed_origins=settings.allowed_origins,
            csrf_cookie=request.cookies.get(policy.csrf_cookie_name),
            csrf_header=request.headers.get("X-CSRF-Token"),
        )
    except ValueError as exc:
        raise ApiProblem(
            status=403,
            code=str(exc).casefold(),
            title="CSRF validation failed",
            detail="The request did not satisfy the CSRF policy.",
        ) from exc
    if session_secret:
        auth.logout(session_secret, now=_now())
    response.delete_cookie(policy.name, path=policy.path)
    response.delete_cookie(policy.csrf_cookie_name, path=policy.path)
    response.headers["Cache-Control"] = "no-store"
    return LogoutResponse()


@router.get("/me", response_model=PrincipalResponse)
def me(
    request: Request,
    organization_id: OrganizationId,
    auth: AuthServiceDependency,
    settings: AuthHttpSettingsDependency,
) -> PrincipalResponse:
    policy = settings.cookie_policy
    try:
        principal = authenticate_http_request(
            HttpAuthInput(
                method=request.method,
                organization_id=organization_id,
                origin=request.headers.get("Origin"),
                authorization=request.headers.get("Authorization"),
                session_cookie=request.cookies.get(policy.name),
                csrf_cookie=request.cookies.get(policy.csrf_cookie_name),
                csrf_header=request.headers.get("X-CSRF-Token"),
            ),
            auth_service=auth,
            now=_now(),
            allowed_origins=settings.allowed_origins,
        )
    except InvalidCredentials as exc:
        raise ApiProblem(
            status=401,
            code="authentication_required",
            title="Authentication required",
            detail="A valid session or API token is required.",
        ) from exc
    return PrincipalResponse(
        actor_id=principal.actor_id,
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        roles=principal.roles,
        permissions=principal.permissions,
    )
