from __future__ import annotations

from dataclasses import asdict
from typing import Awaitable, Callable, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from lumi_project_core.governance import (
    AuditQuery,
    GovernanceActor,
    GovernanceEngine,
    GovernanceError,
)

GovernanceActorResolver = Callable[[Request], Awaitable[GovernanceActor]]
AuditResultInput = Literal["SUCCESS", "DENIED", "FAILED"]
RetentionClassInput = Literal[
    "SECURITY_AUDIT",
    "BILLING",
    "CONTENT",
    "AGENT_TRACE",
    "TEMP_SANDBOX",
    "EXPORT",
    "ANALYTICS",
]
HoldTypeInput = Literal["LEGAL", "BILLING"]
HoldScopeInput = Literal["USER", "ORGANIZATION", "RESOURCE", "RETENTION_CLASS"]
ExportFormatInput = Literal["JSON", "CSV"]


class AuditCorrectionBody(BaseModel):
    reason_code: str = Field(min_length=1, max_length=160)
    note: str = Field(min_length=1, max_length=1000)


class RetentionPolicyBody(BaseModel):
    retention_class: RetentionClassInput
    version: int = Field(ge=1)
    retention_days: int = Field(ge=1, le=36500)
    policy_note: str = Field(min_length=1, max_length=1000)


class LegalHoldBody(BaseModel):
    hold_type: HoldTypeInput
    organization_id: str | None = Field(default=None, max_length=160)
    scope_type: HoldScopeInput
    scope_id: str = Field(min_length=1, max_length=300)
    reason_code: str = Field(min_length=1, max_length=160)
    ticket_ref: str = Field(min_length=1, max_length=160)


class ReleaseHoldBody(BaseModel):
    reason_code: str = Field(min_length=1, max_length=160)
    ticket_ref: str = Field(min_length=1, max_length=160)


class DeletionRequestBody(BaseModel):
    subject_user_id: str = Field(min_length=1, max_length=160)
    organization_id: str = Field(min_length=1, max_length=160)
    request_id: str | None = Field(default=None, max_length=160)
    reason_code: str = Field(default="DATA_SUBJECT_REQUEST", min_length=1, max_length=160)


class AuditExportBody(BaseModel):
    export_format: ExportFormatInput
    organization_id: str | None = Field(default=None, max_length=160)
    actor_id: str | None = Field(default=None, max_length=160)
    action: str | None = Field(default=None, max_length=240)
    resource_type: str | None = Field(default=None, max_length=160)
    resource_id: str | None = Field(default=None, max_length=240)
    result: AuditResultInput | None = None
    trace_id: str | None = Field(default=None, max_length=160)
    start_at: str | None = None
    end_at: str | None = None


def _request_id(request: Request) -> str | None:
    value = request.headers.get("x-request-id")
    return value[:160] if value else None


def _problem(error: GovernanceError, request_id: str | None) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail={
            "code": error.code,
            "message": "Governance request could not be completed.",
            "request_id": request_id,
        },
    )


def _require_permission(actor: GovernanceActor, permission: str) -> None:
    if permission not in actor.permissions:
        raise GovernanceError("GOVERNANCE_FORBIDDEN", 403)


def _query(
    *,
    organization_id: str | None,
    actor_id: str | None,
    action: str | None,
    resource_type: str | None,
    resource_id: str | None,
    result: AuditResultInput | None,
    trace_id: str | None,
    start_at: str | None,
    end_at: str | None,
    cursor: str | None,
    limit: int,
) -> AuditQuery:
    return AuditQuery(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        trace_id=trace_id,
        start_at=start_at,
        end_at=end_at,
        cursor=cursor,
        limit=limit,
    )


def create_governance_router(
    *, engine: GovernanceEngine, resolve_actor: GovernanceActorResolver
) -> APIRouter:
    router = APIRouter(prefix="/governance", tags=["governance"])

    @router.get("/capabilities")
    async def capabilities(request: Request):
        actor = await resolve_actor(request)
        platform_read = actor.actor_type == "PLATFORM_ADMIN" and "admin.audit.read" in actor.permissions
        return {
            "can_read_audit": platform_read or "audit.read" in actor.permissions,
            "can_export_audit": "audit.export" in actor.permissions,
            "can_manage_retention": "governance.retention.manage" in actor.permissions,
            "can_manage_holds": "governance.legal_hold.manage" in actor.permissions,
            "can_manage_deletion": "governance.deletion.manage" in actor.permissions,
        }

    @router.get("/audit")
    async def search_audit(
        request: Request,
        organization_id: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: AuditResultInput | None = None,
        trace_id: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ):
        actor = await resolve_actor(request)
        try:
            page = engine.search_audit(
                actor,
                _query(
                    organization_id=organization_id,
                    actor_id=actor_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    result=result,
                    trace_id=trace_id,
                    start_at=start_at,
                    end_at=end_at,
                    cursor=cursor,
                    limit=limit,
                ),
            )
            return {"items": [asdict(item) for item in page.items], "next_cursor": page.next_cursor}
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/audit/{event_id}:correct")
    async def correct_audit(request: Request, event_id: str, body: AuditCorrectionBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                engine.correct_audit(
                    actor,
                    event_id=event_id,
                    reason_code=body.reason_code,
                    note=body.note,
                    request_id=_request_id(request),
                )
            )
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/retention/policies")
    async def retention_policies(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in engine.list_retention_policies(actor)]}
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/retention/policies")
    async def publish_retention(request: Request, body: RetentionPolicyBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                engine.publish_retention_policy(
                    actor,
                    retention_class=body.retention_class,
                    version=body.version,
                    retention_days=body.retention_days,
                    policy_note=body.policy_note,
                )
            )
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/retention/candidates")
    async def retention_candidates(request: Request, organization_id: str | None = None):
        actor = await resolve_actor(request)
        try:
            return {
                "items": [
                    asdict(item)
                    for item in engine.retention_candidates(actor, organization_id=organization_id)
                ]
            }
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/legal-holds")
    async def legal_holds(request: Request, organization_id: str | None = None):
        actor = await resolve_actor(request)
        try:
            return {
                "items": [asdict(item) for item in engine.active_holds(actor, organization_id=organization_id)]
            }
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/legal-holds")
    async def create_hold(request: Request, body: LegalHoldBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                engine.create_hold(
                    actor,
                    hold_type=body.hold_type,
                    organization_id=body.organization_id,
                    scope_type=body.scope_type,
                    scope_id=body.scope_id,
                    reason_code=body.reason_code,
                    ticket_ref=body.ticket_ref,
                )
            )
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/legal-holds/{hold_id}:release")
    async def release_hold(request: Request, hold_id: str, body: ReleaseHoldBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                engine.release_hold(
                    actor,
                    hold_id=hold_id,
                    reason_code=body.reason_code,
                    ticket_ref=body.ticket_ref,
                )
            )
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/deletions")
    async def deletions(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in engine.list_deletions(actor)]}
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/deletions")
    async def request_deletion(request: Request, body: DeletionRequestBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                engine.request_deletion(
                    actor,
                    subject_user_id=body.subject_user_id,
                    organization_id=body.organization_id,
                    request_id=body.request_id,
                    reason_code=body.reason_code,
                )
            )
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/deletions/{deletion_request_id}:execute")
    async def execute_deletion(request: Request, deletion_request_id: str):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.execute_deletion(actor, deletion_request_id))
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/audit/exports")
    async def list_exports(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in engine.list_exports(actor)]}
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/audit/exports")
    async def create_export(request: Request, body: AuditExportBody):
        actor = await resolve_actor(request)
        try:
            _require_permission(actor, "audit.export")
            return asdict(
                engine.create_export(
                    actor,
                    export_format=body.export_format,
                    query=_query(
                        organization_id=body.organization_id,
                        actor_id=body.actor_id,
                        action=body.action,
                        resource_type=body.resource_type,
                        resource_id=body.resource_id,
                        result=body.result,
                        trace_id=body.trace_id,
                        start_at=body.start_at,
                        end_at=body.end_at,
                        cursor=None,
                        limit=200,
                    ),
                )
            )
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/audit/exports/{job_id}")
    async def get_export(request: Request, job_id: str):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.get_export(actor, job_id))
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/audit/exports/{job_id}:download")
    async def get_download(request: Request, job_id: str, ttl_seconds: int = 300):
        actor = await resolve_actor(request)
        try:
            _require_permission(actor, "audit.export")
            return asdict(engine.get_download(actor, job_id, ttl_seconds=ttl_seconds))
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/internal/audit/exports/{job_id}:run")
    async def run_export(request: Request, job_id: str):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.run_export(actor, job_id))
        except GovernanceError as error:
            raise _problem(error, _request_id(request)) from error

    return router
