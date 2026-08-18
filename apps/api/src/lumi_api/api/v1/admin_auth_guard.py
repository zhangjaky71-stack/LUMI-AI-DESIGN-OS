from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request

from lumi_api.auth import HttpAuthInput, InvalidCredentials, authenticate_http_request, build_request_context

from .auth_dependencies import AuthHttpSettingsDependency, AuthServiceDependency
from .errors import ApiProblem
from .headers import OrganizationId


def establish_platform_admin_identity(
    request: Request,
    organization_id: OrganizationId,
    auth: AuthServiceDependency,
    settings: AuthHttpSettingsDependency,
) -> None:
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
            now=datetime.now(UTC),
            allowed_origins=settings.allowed_origins,
        )
    except InvalidCredentials as exc:
        raise ApiProblem(
            status=401,
            code="platform_admin_auth_failed",
            title="Platform admin authentication failed",
            detail="Valid user authentication is required.",
        ) from exc
    if principal.user_id is None:
        raise ApiProblem(
            status=403,
            code="platform_admin_user_principal_required",
            title="Platform admin user principal required",
            detail="API tokens and service principals cannot enter the platform admin control plane.",
        )
    request.state.platform_admin_user_id = principal.user_id
    request.state.lumi_context = build_request_context(
        principal=principal,
        request_id=request.headers.get("X-Request-ID", "unassigned"),
        trace_id=request.headers.get("traceparent", request.headers.get("X-Request-ID", "unassigned")),
        organization_id=organization_id,
    )
