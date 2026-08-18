from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from lumi_api.approvals import (
    ApprovalAuditEntry,
    ApprovalConflict,
    ApprovalEffect,
    ApprovalForbidden,
    ApprovalNotFound,
    ApprovalRecord,
    ApprovalStale,
    ApprovalStatus,
)

from .approval_dependencies import ApprovalServiceDependency
from .approval_schemas import (
    ApprovalAuditResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalEffectResponse,
    ApprovalResponse,
    CreateArtifactApprovalRequest,
)
from .common import ProblemDetail
from .errors import ApiProblem
from .headers import IdempotencyKey, OrganizationId

router = APIRouter(prefix="/api/v1", tags=["approvals"])

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _now() -> datetime:
    return datetime.now(UTC)


def _operation_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="approval_idempotency_key_must_be_uuid",
            title="Invalid Idempotency-Key",
            detail="Approval writes require a UUID Idempotency-Key.",
        ) from exc


def _context(request: Request) -> tuple[str, tuple[str, ...]]:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    permissions = getattr(context, "permissions", ())
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="authenticated_actor_required",
            title="Authenticated actor required",
            detail="Approval actions require an authenticated user actor.",
        )
    return str(actor_id), tuple(str(item) for item in permissions)


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, ApprovalNotFound):
        return ApiProblem(
            status=404,
            code=str(exc).casefold(),
            title="Approval resource not found",
            detail=str(exc),
        )
    if isinstance(exc, ApprovalForbidden):
        return ApiProblem(
            status=403,
            code=str(exc).casefold(),
            title="Approval action forbidden",
            detail=str(exc),
        )
    if isinstance(exc, ApprovalStale):
        return ApiProblem(
            status=409,
            code="approval_stale",
            title="Approval is stale",
            detail=str(exc),
        )
    if isinstance(exc, ApprovalConflict):
        return ApiProblem(
            status=409,
            code=str(exc).casefold(),
            title="Approval state conflict",
            detail=str(exc),
        )
    if isinstance(exc, ValueError):
        return ApiProblem(
            status=422,
            code="approval_request_invalid",
            title="Invalid approval request",
            detail=str(exc),
        )
    raise exc


def _approval_response(value: ApprovalRecord) -> ApprovalResponse:
    title = value.payload_summary.get("title")
    summary = value.payload_summary.get("summary")
    return ApprovalResponse(
        id=value.id,
        project_id=value.project_id,
        agent_run_id=value.agent_run_id,
        task_id=value.task_id,
        approval_type=value.approval_type,
        subject_type=value.subject_type,
        subject_id=value.subject_id,
        subject_version_ref=value.subject_version_ref,
        artifact_version_id=value.artifact_version_id,
        status=value.status,
        requested_by=value.requested_by,
        required_permission=value.required_permission,
        policy_mode=value.policy_mode,
        policy_version=value.policy_version,
        min_approvals=value.min_approvals,
        title=str(title) if title else "Approval required",
        summary=str(summary) if summary else "Review the exact subject before deciding.",
        expires_at=value.expires_at,
        resolved_at=value.resolved_at,
        created_at=value.created_at,
        updated_at=value.updated_at,
        version=value.version,
    )


def _effect_response(value: ApprovalEffect) -> ApprovalEffectResponse:
    return ApprovalEffectResponse(
        id=value.id,
        effect_type=value.effect_type,
        status=value.status,
        attempt_count=value.attempt_count,
        has_error=value.last_error is not None,
        completed_at=value.completed_at,
    )


def _audit_response(value: ApprovalAuditEntry) -> ApprovalAuditResponse:
    return ApprovalAuditResponse(
        id=value.id,
        action=value.action,
        actor_id=value.actor_id,
        status_from=value.status_from,
        status_to=value.status_to,
        created_at=value.created_at,
    )


@router.post(
    "/projects/{project_id}/approvals/artifact-version",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
)
def request_artifact_approval(
    project_id: UUID,
    body: CreateArtifactApprovalRequest,
    request: Request,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApprovalServiceDependency,
) -> ApprovalResponse:
    actor_id, _ = _context(request)
    now = _now()
    if body.expires_at is not None:
        if body.expires_at.tzinfo is None or body.expires_at.utcoffset() is None:
            raise ApiProblem(
                status=422,
                code="approval_expiry_timezone_required",
                title="Invalid approval expiry",
                detail="expires_at must be timezone-aware.",
            )
        if body.expires_at <= now:
            raise ApiProblem(
                status=422,
                code="approval_expiry_must_be_future",
                title="Invalid approval expiry",
                detail="expires_at must be in the future.",
            )
    try:
        approval = service.request_artifact_approval(
            organization_id=organization_id,
            project_id=project_id,
            request_operation_id=_operation_id(idempotency_key),
            artifact_version_id=body.artifact_version_id,
            requested_by=actor_id,
            payload_summary={"title": body.title.strip(), "summary": body.summary.strip()},
            expires_at=body.expires_at,
            agent_run_id=None,
            task_id=None,
            interrupt_id=None,
            resume_version=None,
            requested_at=now,
        )
        return _approval_response(approval)
    except (ApprovalNotFound, ApprovalForbidden, ApprovalConflict, ApprovalStale, ValueError) as exc:
        raise _translate(exc) from exc


@router.get(
    "/projects/{project_id}/approvals",
    response_model=tuple[ApprovalResponse, ...],
    responses=_ERROR_RESPONSES,
)
def list_project_approvals(
    project_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: ApprovalServiceDependency,
    status_filter: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> tuple[ApprovalResponse, ...]:
    actor_id, _ = _context(request)
    try:
        return tuple(
            _approval_response(item)
            for item in service.list_project(
                organization_id=organization_id,
                project_id=project_id,
                actor_id=actor_id,
                status=status_filter,
                limit=limit,
            )
        )
    except (ApprovalNotFound, ApprovalForbidden, ApprovalConflict, ApprovalStale, ValueError) as exc:
        raise _translate(exc) from exc


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalResponse,
    responses=_ERROR_RESPONSES,
)
def get_approval(
    approval_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: ApprovalServiceDependency,
) -> ApprovalResponse:
    actor_id, _ = _context(request)
    try:
        return _approval_response(
            service.get(
                organization_id=organization_id,
                approval_id=approval_id,
                actor_id=actor_id,
            )
        )
    except (ApprovalNotFound, ApprovalForbidden, ApprovalConflict, ApprovalStale, ValueError) as exc:
        raise _translate(exc) from exc


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalDecisionResponse,
    responses=_ERROR_RESPONSES,
)
def decide_approval(
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    request: Request,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApprovalServiceDependency,
) -> ApprovalDecisionResponse:
    actor_id, permissions = _context(request)
    feedback = {
        "comment": body.comment,
        "node_ids": [str(item) for item in body.node_ids],
        "requested_changes": list(body.requested_changes),
    }
    try:
        approval, decision, effects = service.decide(
            organization_id=organization_id,
            approval_id=approval_id,
            operation_id=_operation_id(idempotency_key),
            decision=body.decision,
            actor_id=actor_id,
            actor_permissions=permissions,
            reason=body.reason,
            feedback=feedback,
            decided_at=_now(),
        )
        return ApprovalDecisionResponse(
            approval=_approval_response(approval),
            decision_id=decision.id,
            effects=tuple(_effect_response(item) for item in effects),
        )
    except (ApprovalNotFound, ApprovalForbidden, ApprovalConflict, ApprovalStale, ValueError) as exc:
        raise _translate(exc) from exc


@router.get(
    "/approvals/{approval_id}/audit",
    response_model=tuple[ApprovalAuditResponse, ...],
    responses=_ERROR_RESPONSES,
)
def list_approval_audit(
    approval_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: ApprovalServiceDependency,
) -> tuple[ApprovalAuditResponse, ...]:
    actor_id, permissions = _context(request)
    if "admin.audit.read" not in permissions:
        raise ApiProblem(
            status=403,
            code="approval_audit_permission_required",
            title="Approval audit forbidden",
            detail="Reading immutable approval audit requires admin.audit.read.",
        )
    try:
        return tuple(
            _audit_response(item)
            for item in service.list_audit(
                organization_id=organization_id,
                approval_id=approval_id,
                actor_id=actor_id,
            )
        )
    except (ApprovalNotFound, ApprovalForbidden, ApprovalConflict, ApprovalStale, ValueError) as exc:
        raise _translate(exc) from exc


@router.get(
    "/approvals/{approval_id}/effects",
    response_model=tuple[ApprovalEffectResponse, ...],
    responses=_ERROR_RESPONSES,
)
def list_approval_effects(
    approval_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: ApprovalServiceDependency,
) -> tuple[ApprovalEffectResponse, ...]:
    actor_id, _ = _context(request)
    try:
        return tuple(
            _effect_response(item)
            for item in service.list_effects(
                organization_id=organization_id,
                approval_id=approval_id,
                actor_id=actor_id,
            )
        )
    except (ApprovalNotFound, ApprovalForbidden, ApprovalConflict, ApprovalStale, ValueError) as exc:
        raise _translate(exc) from exc
