from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request

from lumi_api.billing import (
    BillingConflict,
    BillingForbidden,
    BillingNotFound,
    InsufficientCredits,
    InvalidWebhook,
)

from .billing_dependencies import BillingFactoryDependency, BillingServiceDependency
from .billing_schemas import (
    BillingOverviewResponse,
    CheckoutRequest,
    CheckoutResponse,
    CreditEntryResponse,
    CreditSummary,
    EntitlementResponse,
    InvoiceResponse,
    PlanSummary,
    PortalRequest,
    PortalResponse,
    SubscriptionSummary,
    WebhookResponse,
)
from .common import ProblemDetail
from .errors import ApiProblem

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/api/v1/billing/webhooks", tags=["billing-webhooks"])

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _permissions(request: Request) -> tuple[str, ...]:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="authenticated_actor_required",
            title="Authenticated actor required",
            detail="Billing actions require an authenticated user actor.",
        )
    return tuple(str(item) for item in getattr(context, "permissions", ()))


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, BillingForbidden):
        return ApiProblem(
            status=403,
            code=exc.code.casefold(),
            title="Billing action forbidden",
            detail=str(exc),
        )
    if isinstance(exc, BillingNotFound):
        return ApiProblem(
            status=404,
            code=exc.code.casefold(),
            title="Billing resource not found",
            detail=str(exc),
        )
    if isinstance(exc, InsufficientCredits):
        return ApiProblem(
            status=409,
            code=exc.code.casefold(),
            title="Insufficient credits",
            detail=str(exc),
        )
    if isinstance(exc, BillingConflict):
        return ApiProblem(
            status=409,
            code=exc.code.casefold(),
            title="Billing state conflict",
            detail=str(exc),
        )
    if isinstance(exc, InvalidWebhook):
        return ApiProblem(
            status=400,
            code=exc.code.casefold(),
            title="Invalid payment webhook",
            detail=str(exc),
        )
    if isinstance(exc, ValueError):
        return ApiProblem(
            status=422,
            code="billing_request_invalid",
            title="Invalid billing request",
            detail=str(exc),
        )
    raise exc


def _overview_response(value) -> BillingOverviewResponse:
    plan = value.plan
    subscription = value.subscription
    return BillingOverviewResponse(
        plan=(
            PlanSummary(
                id=plan.id,
                key=plan.plan_key,
                name=plan.plan_name,
                version=plan.version,
                currency=plan.currency,
                monthly_price=plan.monthly_price,
                included_credits=plan.included_credits,
            )
            if plan is not None
            else None
        ),
        subscription=(
            SubscriptionSummary(
                id=subscription.id,
                state=subscription.state,
                current_period_end=subscription.current_period_end,
                cancel_at_period_end=subscription.cancel_at_period_end,
            )
            if subscription is not None
            else None
        ),
        credits=CreditSummary(
            balance=value.wallet.balance,
            allow_postpaid=value.wallet.allow_postpaid,
        ),
        entitlements=EntitlementResponse(
            state=value.entitlements.subscription_state,
            plan_version_id=value.entitlements.plan_version_id,
            entitlements=value.entitlements.entitlements,
            credits_balance=value.entitlements.credits_balance,
            can_consume_paid_features=value.entitlements.can_consume_paid_features,
        ),
    )


@router.get("/overview", response_model=BillingOverviewResponse, responses=_ERROR_RESPONSES)
def get_overview(
    request: Request,
    service: BillingServiceDependency,
) -> BillingOverviewResponse:
    try:
        return _overview_response(service.overview(permissions=_permissions(request)))
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/entitlements", response_model=EntitlementResponse, responses=_ERROR_RESPONSES)
def get_entitlements(
    request: Request,
    service: BillingServiceDependency,
) -> EntitlementResponse:
    try:
        value = service.entitlements(permissions=_permissions(request))
        return EntitlementResponse(
            state=value.subscription_state,
            plan_version_id=value.plan_version_id,
            entitlements=value.entitlements,
            credits_balance=value.credits_balance,
            can_consume_paid_features=value.can_consume_paid_features,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/credits", response_model=list[CreditEntryResponse], responses=_ERROR_RESPONSES)
def get_credits(
    request: Request,
    service: BillingServiceDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[CreditEntryResponse]:
    try:
        entries = service.list_credits(permissions=_permissions(request), limit=limit)
        return [
            CreditEntryResponse(
                id=item.id,
                event_type=item.event_type.value,
                amount=item.amount,
                reason=item.reason,
                reference_type=item.reference_type,
                reference_id=item.reference_id,
                pricing_policy_version=item.pricing_policy_version,
                created_at=item.created_at,
            )
            for item in entries
        ]
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/invoices", response_model=list[InvoiceResponse], responses=_ERROR_RESPONSES)
def get_invoices(
    request: Request,
    service: BillingServiceDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[InvoiceResponse]:
    try:
        rows = service.list_invoices(permissions=_permissions(request), limit=limit)
        return [
            InvoiceResponse(
                provider_invoice_ref=str(row["provider_invoice_ref"]),
                status=str(row["status"]),
                amount_due=Decimal(row["amount_due"]),
                currency=str(row["currency"]),
                hosted_invoice_url=row["hosted_invoice_url"],
                period_start=row["period_start"],
                period_end=row["period_end"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/checkout", response_model=CheckoutResponse, responses=_ERROR_RESPONSES)
def create_checkout(
    body: CheckoutRequest,
    request: Request,
    service: BillingServiceDependency,
) -> CheckoutResponse:
    try:
        value = service.create_checkout(
            permissions=_permissions(request),
            plan_version_id=body.plan_version_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        return CheckoutResponse(
            provider=value.provider,
            url=value.url,
            session_ref=value.provider_session_ref,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/portal", response_model=PortalResponse, responses=_ERROR_RESPONSES)
def create_portal(
    body: PortalRequest,
    request: Request,
    service: BillingServiceDependency,
) -> PortalResponse:
    try:
        value = service.create_portal(
            permissions=_permissions(request),
            return_url=body.return_url,
        )
        return PortalResponse(provider=value.provider, url=value.url)
    except Exception as exc:
        raise _translate(exc) from exc


@webhook_router.post("/mock", response_model=WebhookResponse, responses=_ERROR_RESPONSES)
async def mock_payment_webhook(
    request: Request,
    factory: BillingFactoryDependency,
    signature: Annotated[str, Header(alias="X-Lumi-Mock-Signature")],
) -> WebhookResponse:
    body = await request.body()
    if len(body) > 256_000:
        raise ApiProblem(
            status=413,
            code="billing_webhook_too_large",
            title="Payment webhook too large",
            detail="Mock payment webhook payload exceeds 256 KB.",
        )
    try:
        status = factory.handle_webhook(body=body, signature=signature)
        return WebhookResponse(status=status.value)
    except Exception as exc:
        raise _translate(exc) from exc
