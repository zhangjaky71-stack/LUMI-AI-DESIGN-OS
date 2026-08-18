from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BillingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SubscriptionState(StrEnum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCEL_AT_PERIOD_END = "CANCEL_AT_PERIOD_END"
    CANCELLED = "CANCELLED"
    INCOMPLETE = "INCOMPLETE"


class CreditEventType(StrEnum):
    GRANT = "GRANT"
    CONSUME = "CONSUME"
    REFUND = "REFUND"
    EXPIRE = "EXPIRE"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class PaymentEventStatus(StrEnum):
    RECEIVED = "RECEIVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


class BillingError(RuntimeError):
    code = "BILLING_ERROR"


class BillingNotFound(BillingError):
    code = "BILLING_NOT_FOUND"


class BillingForbidden(BillingError):
    code = "BILLING_FORBIDDEN"


class BillingConflict(BillingError):
    code = "BILLING_CONFLICT"


class InsufficientCredits(BillingConflict):
    code = "BILLING_INSUFFICIENT_CREDITS"


class InvalidWebhook(BillingError):
    code = "BILLING_INVALID_WEBHOOK"


class PlanVersionRecord(BillingModel):
    id: UUID
    plan_id: UUID
    plan_key: str = Field(min_length=1, max_length=80)
    plan_name: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    monthly_price: Decimal = Field(ge=0)
    included_credits: Decimal = Field(ge=0)
    postpaid_allowed: bool = False
    entitlements: dict[str, Any] = Field(default_factory=dict)
    pricing_policy: dict[str, Any] = Field(default_factory=dict)
    effective_at: datetime
    retired_at: datetime | None = None


class SubscriptionRecord(BillingModel):
    id: UUID
    organization_id: UUID
    billing_account_id: UUID
    plan_version_id: UUID
    provider: str
    provider_subscription_ref: str
    state: SubscriptionState
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    created_at: datetime
    updated_at: datetime


class CreditWalletRecord(BillingModel):
    id: UUID
    organization_id: UUID
    balance: Decimal
    allow_postpaid: bool
    updated_at: datetime


class CreditLedgerEntry(BillingModel):
    id: UUID
    organization_id: UUID
    wallet_id: UUID
    operation_id: UUID
    event_type: CreditEventType
    amount: Decimal
    reason: str
    reference_type: str | None = None
    reference_id: str | None = None
    pricing_policy_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EntitlementSnapshot(BillingModel):
    organization_id: UUID
    subscription_state: SubscriptionState | None
    plan_version_id: UUID | None
    entitlements: dict[str, Any]
    credits_balance: Decimal
    can_consume_paid_features: bool


class CheckoutSession(BillingModel):
    provider: str
    url: str
    provider_session_ref: str


class PortalSession(BillingModel):
    provider: str
    url: str


class NormalizedPaymentEvent(BillingModel):
    provider: str
    provider_event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=120)
    organization_id: UUID
    occurred_at: datetime
    subscription_ref: str | None = None
    plan_key: str | None = None
    plan_version: int | None = Field(default=None, ge=1)
    subscription_state: SubscriptionState | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    invoice_ref: str | None = None
    invoice_status: str | None = None
    invoice_amount: Decimal | None = None
    currency: str | None = None
    hosted_invoice_url: str | None = None
    credit_grant: Decimal | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillingOverview(BillingModel):
    organization_id: UUID
    plan: PlanVersionRecord | None
    subscription: SubscriptionRecord | None
    wallet: CreditWalletRecord
    entitlements: EntitlementSnapshot


class PaymentProvider(Protocol):
    name: str

    def create_customer(self, *, organization_id: UUID) -> str: ...

    def create_checkout(
        self,
        *,
        organization_id: UUID,
        provider_customer_ref: str,
        plan_version: PlanVersionRecord,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    def create_portal_session(
        self, *, provider_customer_ref: str, return_url: str
    ) -> PortalSession: ...

    def verify_webhook(self, *, body: bytes, signature: str) -> NormalizedPaymentEvent: ...


def require_positive_credit_amount(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("BILLING_CREDIT_DECIMAL_REQUIRED")
    if value <= 0:
        raise ValueError("BILLING_CREDIT_AMOUNT_MUST_BE_POSITIVE")
    return value
