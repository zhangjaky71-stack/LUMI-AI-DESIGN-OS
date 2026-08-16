from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hmac
import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from lumi_auth import hash_token
from lumi_project_core.billing import BillingActor, BillingError
from lumi_project_core.stripe_provider import StripePaymentProvider
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.auth.errors import PermissionDenied, SessionInvalid
from lumi_api.auth.principal import PrincipalResolver
from lumi_api.auth.router import CSRF_HEADER, SESSION_COOKIE
from lumi_api.billing_runtime import AsyncStripeBillingRuntime, load_stripe_runtime_config
from lumi_api.config import Settings, get_settings
from lumi_api.persistence.session import create_engine, create_session_factory


def _problem(error: BillingError, request: Request) -> JSONResponse:
    request_id = str(getattr(request.state, "request_id", "missing-request-id"))
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        content={
            "type": f"https://errors.lumi.dev/billing/{error.code.lower().replace('_', '-')}",
            "title": "Billing request could not be completed",
            "status": error.status,
            "code": error.code,
            "detail": "Billing request could not be completed.",
            "request_id": request_id,
            "fields": {},
        },
    )


def _allowed_origins() -> frozenset[str]:
    raw = os.environ.get("LUMI_ALLOWED_ORIGINS", "")
    return frozenset(item.strip().rstrip("/") for item in raw.split(",") if item.strip())


async def _actor(
    request: Request,
    *,
    sessions: async_sessionmaker[AsyncSession],
    permission: Literal["billing.read", "billing.manage"],
    csrf_required: bool,
) -> BillingActor:
    organization_header = request.headers.get("X-Lumi-Organization-Id")
    requested_org: UUID | None = None
    if organization_header:
        try:
            requested_org = UUID(organization_header)
        except ValueError as error:
            raise BillingError("BILLING_ORGANIZATION_ID_INVALID", 400) from error

    authorization = request.headers.get("Authorization", "")
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    session_token = request.cookies.get(SESSION_COOKIE)
    now = datetime.now(UTC)
    request_id = str(getattr(request.state, "request_id", "missing-request-id"))
    trace_id = request.headers.get("traceparent", request_id)

    async with sessions() as session:
        async with session.begin():
            resolver = PrincipalResolver(session)
            try:
                if bearer:
                    principal = await resolver.from_api_token(
                        plaintext_token=bearer,
                        required_scope=permission,
                        now=now,
                    )
                    if requested_org is not None and requested_org != principal.organization_id:
                        raise BillingError("BILLING_FORBIDDEN", 403)
                    return BillingActor(
                        actor_id=str(principal.created_by),
                        organization_id=str(principal.organization_id),
                        permissions=frozenset(principal.scopes),
                    )

                if not session_token:
                    raise BillingError("BILLING_AUTHENTICATION_REQUIRED", 401)
                principal = await resolver.from_session(
                    plaintext_session_token=session_token,
                    request_id=request_id,
                    trace_id=trace_id,
                    now=now,
                    requested_organization_id=requested_org,
                )
                if permission not in principal.context.permissions:
                    raise BillingError("BILLING_FORBIDDEN", 403)
                if csrf_required:
                    csrf = request.headers.get(CSRF_HEADER, "")
                    if not csrf or not hmac.compare_digest(
                        hash_token(csrf), principal.csrf_token_hash
                    ):
                        raise BillingError("BILLING_CSRF_INVALID", 403)
                    allowed = _allowed_origins()
                    origin = request.headers.get("Origin", "").strip().rstrip("/")
                    if not allowed or not origin or origin not in allowed:
                        raise BillingError("BILLING_ORIGIN_FORBIDDEN", 403)
                return BillingActor(
                    actor_id=principal.context.actor_id,
                    organization_id=principal.context.organization_id,
                    permissions=frozenset(principal.context.permissions),
                )
            except SessionInvalid as error:
                raise BillingError("BILLING_AUTHENTICATION_REQUIRED", 401) from error
            except PermissionDenied as error:
                raise BillingError("BILLING_FORBIDDEN", 403) from error


def create_stripe_billing_router(
    *,
    runtime: AsyncStripeBillingRuntime,
    sessions: async_sessionmaker[AsyncSession],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

    @router.get("")
    async def summary(request: Request):
        try:
            actor = await _actor(
                request, sessions=sessions, permission="billing.read", csrf_required=False
            )
            return asdict(await runtime.summary(actor))
        except BillingError as error:
            return _problem(error, request)

    @router.post("/checkout")
    async def checkout(request: Request):
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise BillingError("BILLING_CHECKOUT_INVALID")
            plan_version_id = payload.get("plan_version_id")
            if not isinstance(plan_version_id, str) or not plan_version_id.strip():
                raise BillingError("BILLING_PLAN_VERSION_REQUIRED")
            actor = await _actor(
                request, sessions=sessions, permission="billing.manage", csrf_required=True
            )
            return asdict(await runtime.create_checkout(actor, plan_version_id))
        except BillingError as error:
            return _problem(error, request)
        except ValueError:
            return _problem(BillingError("BILLING_CHECKOUT_INVALID"), request)

    @router.post("/portal")
    async def portal(request: Request):
        try:
            actor = await _actor(
                request, sessions=sessions, permission="billing.manage", csrf_required=True
            )
            return asdict(await runtime.create_portal(actor))
        except BillingError as error:
            return _problem(error, request)

    @router.post("/subscription:cancel")
    async def cancel(request: Request):
        try:
            actor = await _actor(
                request, sessions=sessions, permission="billing.manage", csrf_required=True
            )
            return asdict(await runtime.cancel_subscription(actor))
        except BillingError as error:
            return _problem(error, request)

    @router.post("/webhooks/stripe")
    async def stripe_webhook(
        request: Request,
        stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    ):
        if not stripe_signature:
            return _problem(BillingError("BILLING_WEBHOOK_SIGNATURE_REQUIRED", 401), request)
        raw_body = await request.body()
        try:
            return asdict(await runtime.process_webhook(raw_body, stripe_signature))
        except BillingError as error:
            if error.code == "BILLING_STRIPE_EVENT_UNSUPPORTED":
                return {"disposition": "IGNORED"}
            return _problem(error, request)

    return router


def install_stripe_billing(app: FastAPI, *, settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    if resolved.lumi_env not in {"staging", "production"}:
        return
    if not _allowed_origins():
        raise RuntimeError("LUMI_ALLOWED_ORIGINS is required for Stripe billing")
    provider_config, plans = load_stripe_runtime_config(environment=resolved.lumi_env)
    engine = create_engine(resolved)
    sessions = create_session_factory(engine)
    runtime = AsyncStripeBillingRuntime(
        session_factory=sessions,
        payment_provider=StripePaymentProvider(provider_config),
        plan_catalog=plans,
    )
    app.include_router(create_stripe_billing_router(runtime=runtime, sessions=sessions))
    app.state.stripe_billing_runtime = runtime
    app.state.stripe_billing_engine = engine

    async def startup() -> None:
        await runtime.initialize_catalog()

    async def shutdown() -> None:
        await engine.dispose()

    app.add_event_handler("startup", startup)
    app.add_event_handler("shutdown", shutdown)
