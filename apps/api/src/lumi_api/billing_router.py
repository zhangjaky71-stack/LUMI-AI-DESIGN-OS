from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from typing import Annotated, Awaitable, Callable

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from lumi_project_core.billing import BillingActor, BillingEngine, BillingError

BillingActorResolver = Callable[[Request], Awaitable[BillingActor]]


class CheckoutBody(BaseModel):
    plan_version_id: str


class UsageQuoteBody(BaseModel):
    pricing_policy_version: int
    usage_key: str
    quantity: str


def _problem(error: BillingError, request_id: str | None) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail={
            "code": error.code,
            "message": "Billing request could not be completed.",
            "request_id": request_id,
        },
    )


def create_billing_router(*, engine: BillingEngine, resolve_actor: BillingActorResolver) -> APIRouter:
    router = APIRouter(prefix="/billing", tags=["billing"])

    @router.get("")
    async def get_billing(request: Request):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.summary(actor))
        except BillingError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/checkout")
    async def create_checkout(request: Request, body: CheckoutBody):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.create_checkout(actor, body.plan_version_id))
        except BillingError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/portal")
    async def create_portal(request: Request):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.create_portal(actor))
        except BillingError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/subscription:cancel")
    async def cancel_subscription(request: Request):
        actor = await resolve_actor(request)
        try:
            return asdict(engine.cancel_subscription(actor))
        except BillingError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/usage:quote")
    async def quote_usage(request: Request, body: UsageQuoteBody):
        actor = await resolve_actor(request)
        try:
            quantity = Decimal(body.quantity)
            return {
                "credits": engine.quote_usage(
                    actor, body.pricing_policy_version, body.usage_key, quantity
                )
            }
        except InvalidOperation as error:
            raise _problem(
                BillingError("BILLING_USAGE_QUANTITY_INVALID"), _request_id(request)
            ) from error
        except BillingError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/webhooks/{provider}")
    async def payment_webhook(
        request: Request,
        provider: str,
        payment_signature: Annotated[str, Header(alias="X-Lumi-Payment-Signature")],
    ):
        if provider.upper() != engine.payment_provider_name.upper():
            raise _problem(
                BillingError("BILLING_PAYMENT_PROVIDER_MISMATCH", 404), _request_id(request)
            )
        raw = await request.body()
        try:
            return asdict(engine.process_webhook(raw, payment_signature))
        except BillingError as error:
            raise _problem(error, _request_id(request)) from error

    return router


def _request_id(request: Request) -> str | None:
    value = request.headers.get("x-request-id")
    return value[:128] if value else None
