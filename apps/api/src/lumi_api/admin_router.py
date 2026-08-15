from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Awaitable, Callable, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from lumi_project_core.admin_console import (
    AdminConsoleService,
    AdminError,
    PlatformAdminActor,
    SensitiveActionConfirmation,
)
from lumi_project_core.billing import BillingError

PlatformAdminActorResolver = Callable[[Request], Awaitable[PlatformAdminActor]]
RegistryKindInput = Literal["AGENT", "SKILL"]
AdminApiError = AdminError | BillingError


class SensitiveActionBody(BaseModel):
    action_summary: str = Field(min_length=1, max_length=240)
    impact_scope: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=1000)
    ticket_ref: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=32)


class RevealPiiBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    ticket_ref: str = Field(min_length=1, max_length=160)


class ViewAsBody(BaseModel):
    organization_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=1000)
    ticket_ref: str = Field(min_length=1, max_length=160)
    ttl_minutes: int = Field(default=10, ge=1, le=15)


class EndViewAsBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    ticket_ref: str = Field(min_length=1, max_length=160)


class ProviderDisableBody(SensitiveActionBody):
    expires_at: str


class RegistryChangeBody(SensitiveActionBody):
    enabled: bool


class BillingAdjustmentBody(SensitiveActionBody):
    delta_credits: int


def _confirmation(body: SensitiveActionBody) -> SensitiveActionConfirmation:
    return SensitiveActionConfirmation(
        action_summary=body.action_summary,
        impact_scope=body.impact_scope,
        reason=body.reason,
        ticket_ref=body.ticket_ref,
        confirmation=body.confirmation,
    )


def _request_id(request: Request) -> str | None:
    value = request.headers.get("x-request-id")
    return value[:128] if value else None


def _problem(error: AdminApiError, request_id: str | None) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail={
            "code": error.code,
            "message": "Platform admin request could not be completed.",
            "request_id": request_id,
        },
    )


def create_admin_router(
    *, service: AdminConsoleService, resolve_actor: PlatformAdminActorResolver
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["platform-admin"])

    @router.get("/console")
    async def console(request: Request):
        actor = await resolve_actor(request)
        try:
            payload: dict[str, object] = {
                "actor": {
                    "actor_id": actor.actor_id,
                    "roles": sorted(actor.roles),
                    "permissions": sorted(actor.permissions),
                },
                "overview": asdict(service.overview(actor)),
                "users": [],
                "runs": [],
                "providers": [],
                "queue": [],
                "registry": [],
                "audit": [],
            }
            if "admin.user.read" in actor.permissions:
                payload["users"] = [asdict(item) for item in service.search_users(actor)]
                payload["runs"] = [asdict(item) for item in service.search_runs(actor)]
            if "admin.provider.read" in actor.permissions:
                payload["providers"] = [asdict(item) for item in service.list_providers(actor)]
            if "admin.queue.read" in actor.permissions:
                payload["queue"] = [asdict(item) for item in service.list_queue(actor)]
            if actor.permissions.intersection(
                {"admin.agent_registry.manage", "admin.skill_registry.manage"}
            ):
                payload["registry"] = [asdict(item) for item in service.list_registry(actor)]
            if "admin.audit.read" in actor.permissions:
                payload["audit"] = [asdict(item) for item in service.recent_audit(actor)]
            return payload
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/users")
    async def users(request: Request, q: str = ""):
        actor = await resolve_actor(request)
        try:
            if len(q) > 160:
                raise AdminError("ADMIN_QUERY_TOO_LONG")
            return {"items": [asdict(item) for item in service.search_users(actor, q)]}
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/users/{user_id}:reveal-pii")
    async def reveal_pii(request: Request, user_id: str, body: RevealPiiBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.reveal_pii(
                    actor,
                    user_id=user_id,
                    reason=body.reason,
                    ticket_ref=body.ticket_ref,
                )
            )
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/users/{user_id}:view-as")
    async def start_view_as(request: Request, user_id: str, body: ViewAsBody):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.start_view_as(
                    actor,
                    target_user_id=user_id,
                    target_organization_id=body.organization_id,
                    reason=body.reason,
                    ticket_ref=body.ticket_ref,
                    ttl_minutes=body.ttl_minutes,
                )
            )
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/view-as/{session_id}:end")
    async def end_view_as(
        request: Request,
        session_id: str,
        body: EndViewAsBody,
    ):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.end_view_as(
                    actor,
                    session_id=session_id,
                    reason=body.reason,
                    ticket_ref=body.ticket_ref,
                )
            )
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/runs")
    async def runs(request: Request, q: str = ""):
        actor = await resolve_actor(request)
        try:
            if len(q) > 160:
                raise AdminError("ADMIN_QUERY_TOO_LONG")
            return {"items": [asdict(item) for item in service.search_runs(actor, q)]}
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/runs/{run_id}:retry")
    async def retry_run(request: Request, run_id: str, body: SensitiveActionBody):
        actor = await resolve_actor(request)
        try:
            return asdict(service.retry_run(actor, run_id, _confirmation(body)))
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/runs/{run_id}:cancel")
    async def cancel_run(request: Request, run_id: str, body: SensitiveActionBody):
        actor = await resolve_actor(request)
        try:
            return asdict(service.cancel_run(actor, run_id, _confirmation(body)))
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/providers")
    async def providers(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in service.list_providers(actor)]}
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/providers/{provider_id}:disable")
    async def disable_provider(
        request: Request,
        provider_id: str,
        body: ProviderDisableBody,
    ):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.disable_provider_temporarily(
                    actor,
                    provider_id=provider_id,
                    expires_at=body.expires_at,
                    confirmation=_confirmation(body),
                )
            )
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/queue")
    async def queue(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in service.list_queue(actor)]}
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/queue/{queue_item_id}:requeue")
    async def requeue(
        request: Request,
        queue_item_id: str,
        body: SensitiveActionBody,
    ):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.requeue(
                    actor,
                    queue_item_id=queue_item_id,
                    confirmation=_confirmation(body),
                )
            )
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/registry")
    async def registry(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in service.list_registry(actor)]}
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/registry/{kind}/{registry_id}:set-enabled")
    async def set_registry_enabled(
        request: Request,
        kind: RegistryKindInput,
        registry_id: str,
        body: RegistryChangeBody,
    ):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.set_registry_enabled(
                    actor,
                    kind=kind,
                    registry_id=registry_id,
                    enabled=body.enabled,
                    confirmation=_confirmation(body),
                )
            )
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/billing/{organization_id}")
    async def billing(request: Request, organization_id: str):
        actor = await resolve_actor(request)
        try:
            return asdict(service.billing_summary(actor, organization_id))
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/billing/{organization_id}:adjust")
    async def adjust_billing(
        request: Request,
        organization_id: str,
        body: BillingAdjustmentBody,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ):
        actor = await resolve_actor(request)
        try:
            return asdict(
                service.adjust_billing(
                    actor,
                    organization_id=organization_id,
                    delta_credits=body.delta_credits,
                    idempotency_key=idempotency_key,
                    confirmation=_confirmation(body),
                )
            )
        except (AdminError, BillingError) as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/audit")
    async def audit(request: Request):
        actor = await resolve_actor(request)
        try:
            return {"items": [asdict(item) for item in service.recent_audit(actor)]}
        except AdminError as error:
            raise _problem(error, _request_id(request)) from error

    return router
