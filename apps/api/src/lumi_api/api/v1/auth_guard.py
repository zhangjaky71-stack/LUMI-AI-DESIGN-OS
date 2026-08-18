from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request

from lumi_api.auth import (
    HttpAuthInput,
    InvalidCredentials,
    Permission,
    authenticate_http_request,
    build_request_context,
)
from lumi_api.observability import bind_business_refs, current_telemetry_context

from .auth_dependencies import AuthHttpSettingsDependency, AuthServiceDependency
from .errors import ApiProblem
from .headers import OrganizationId


def _permission_for_request(request: Request) -> Permission:
    method = request.method.upper()
    path = request.url.path
    if method in {"POST", "PUT", "PATCH"} and (
        path.endswith("/assets/uploads")
        or "/assets/uploads/" in path
    ):
        return Permission.ASSET_UPLOAD
    if method in {"GET", "HEAD"}:
        return Permission.PROJECT_READ
    return Permission.PROJECT_WRITE


def enforce_api_auth(
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
        code = str(exc)
        status = 404 if code == "TENANT_RESOURCE_NOT_FOUND" else 401
        raise ApiProblem(
            status=status,
            code=code.casefold(),
            title="Request authorization failed",
            detail="The requested resource is unavailable or authentication is invalid.",
        ) from exc
    except ValueError as exc:
        code = str(exc)
        if code.startswith("CSRF_"):
            raise ApiProblem(
                status=403,
                code=code.casefold(),
                title="CSRF validation failed",
                detail="The request did not satisfy the CSRF policy.",
            ) from exc
        raise

    permission = _permission_for_request(request)
    decision = auth.policy.authorize(
        principal,
        organization_id=organization_id,
        permission=permission,
    )
    if not decision.allowed:
        status = 404 if decision.reason_code == "TENANT_RESOURCE_NOT_FOUND" else 403
        raise ApiProblem(
            status=status,
            code=decision.reason_code.casefold(),
            title="Request authorization failed",
            detail="The principal is not authorized for this operation.",
        )

    telemetry_context = bind_business_refs(organization_id=organization_id)
    if telemetry_context is None:
        telemetry_context = current_telemetry_context()
    request_id = getattr(request.state, "request_id", "unassigned")
    trace_id = telemetry_context.trace_id if telemetry_context is not None else request_id
    request.state.lumi_context = build_request_context(
        principal=principal,
        request_id=request_id,
        trace_id=trace_id,
        organization_id=organization_id,
    )
