from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from lumi_api.governance import (
    AuditExportRequest,
    AuditResult,
    AuditSearch,
    GovernanceConflict,
    GovernanceForbidden,
    GovernanceNotFound,
    GovernanceUnavailable,
)

from .common import ProblemDetail
from .errors import ApiProblem
from .governance_dependencies import GovernanceServiceDependency
from .governance_schemas import (
    AuditExportInput,
    DeletionRequestInput,
    LegalHoldRequest,
    ReasonRequest,
)
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])
_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _context(request: Request) -> tuple[UUID, tuple[str, ...]]:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="governance_user_actor_required",
            title="User actor required",
            detail="Governance actions require an authenticated user actor.",
        )
    try:
        user_id = UUID(str(actor_id))
    except ValueError as exc:
        raise ApiProblem(
            status=403,
            code="governance_human_actor_required",
            title="Human actor required",
            detail="This governance operation requires a human user principal.",
        ) from exc
    permissions = tuple(str(item) for item in getattr(context, "permissions", ()))
    return user_id, permissions


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, GovernanceForbidden):
        return ApiProblem(403, exc.code.casefold(), "Governance action forbidden", str(exc))
    if isinstance(exc, GovernanceNotFound):
        return ApiProblem(404, exc.code.casefold(), "Governance resource not found", str(exc))
    if isinstance(exc, GovernanceConflict):
        return ApiProblem(409, exc.code.casefold(), "Governance state conflict", str(exc))
    if isinstance(exc, GovernanceUnavailable):
        return ApiProblem(503, exc.code.casefold(), "Governance operation unavailable", str(exc))
    if isinstance(exc, ValueError):
        return ApiProblem(422, "governance_request_invalid", "Invalid governance request", str(exc))
    raise exc


@router.get("/audit", responses=_ERROR_RESPONSES)
def search_audit(
    request: Request,
    organization_id: OrganizationId,
    service: GovernanceServiceDependency,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: AuditResult | None = None,
    trace_id: str | None = None,
    cursor_occurred_at: datetime | None = None,
    cursor_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    _, permissions = _context(request)
    try:
        return service.search(
            AuditSearch(
                organization_id=organization_id,
                from_time=from_time,
                to_time=to_time,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                trace_id=trace_id,
                cursor_occurred_at=cursor_occurred_at,
                cursor_id=cursor_id,
                limit=limit,
            ),
            permissions=permissions,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/legal-holds", responses=_ERROR_RESPONSES)
def create_legal_hold(
    body: LegalHoldRequest,
    request: Request,
    organization_id: OrganizationId,
    service: GovernanceServiceDependency,
):
    user_id, permissions = _context(request)
    try:
        return service.create_legal_hold(
            organization_id=organization_id,
            hold_key=body.hold_key,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            reason=body.reason,
            actor_user_id=user_id,
            permissions=permissions,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/legal-holds/{hold_id}/release", responses=_ERROR_RESPONSES)
def release_legal_hold(
    hold_id: UUID,
    body: ReasonRequest,
    request: Request,
    organization_id: OrganizationId,
    service: GovernanceServiceDependency,
):
    user_id, permissions = _context(request)
    try:
        return service.release_legal_hold(
            organization_id=organization_id,
            hold_id=hold_id,
            reason=body.reason,
            actor_user_id=user_id,
            permissions=permissions,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/deletion-requests", responses=_ERROR_RESPONSES)
def request_deletion(
    body: DeletionRequestInput,
    request: Request,
    organization_id: OrganizationId,
    service: GovernanceServiceDependency,
):
    user_id, permissions = _context(request)
    try:
        return service.request_deletion(
            organization_id=organization_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            reason=body.reason,
            actor_user_id=user_id,
            permissions=permissions,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/audit-exports", responses=_ERROR_RESPONSES)
def request_audit_export(
    body: AuditExportInput,
    request: Request,
    organization_id: OrganizationId,
    service: GovernanceServiceDependency,
):
    user_id, permissions = _context(request)
    try:
        export_id = service.request_audit_export(
            organization_id=organization_id,
            actor_user_id=user_id,
            request=AuditExportRequest(
                export_format=body.export_format,
                filters=body.filters,
            ),
            permissions=permissions,
        )
        return {"id": str(export_id), "status": "PENDING"}
    except Exception as exc:
        raise _translate(exc) from exc
