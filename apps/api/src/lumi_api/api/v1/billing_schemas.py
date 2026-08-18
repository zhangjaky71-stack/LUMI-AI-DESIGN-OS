from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lumi_api.billing import SubscriptionState


class BillingApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckoutRequest(BillingApiModel):
    plan_version_id: UUID
    success_url: str = Field(min_length=1, max_length=2048)
    cancel_url: str = Field(min_length=1, max_length=2048)

    @field_validator("success_url", "cancel_url")
    @classmethod
    def safe_return_url(cls, value: str) -> str:
        if value.startswith("https://") or value.startswith("http://localhost"):
            return value
        raise ValueError("hosted return URL must use https or localhost")


class CheckoutResponse(BillingApiModel):
    provider: str
    url: str
    session_ref: str


class PortalRequest(BillingApiModel):
    return_url: str = Field(min_length=1, max_length=2048)

    @field_validator("return_url")
    @classmethod
    def safe_return_url(cls, value: str) -> str:
        if value.startswith("https://") or value.startswith("http://localhost"):
            return value
        raise ValueError("hosted return URL must use https or localhost")


class PortalResponse(BillingApiModel):
    provider: str
    url: str


class PlanSummary(BillingApiModel):
    id: UUID
    key: str
    name: str
    version: int
    currency: str
    monthly_price: Decimal
    included_credits: Decimal


class SubscriptionSummary(BillingApiModel):
    id: UUID
    state: SubscriptionState
    current_period_end: datetime | None
    cancel_at_period_end: bool


class CreditSummary(BillingApiModel):
    balance: Decimal
    allow_postpaid: bool


class EntitlementResponse(BillingApiModel):
    state: SubscriptionState | None
    plan_version_id: UUID | None
    entitlements: dict[str, Any]
    credits_balance: Decimal
    can_consume_paid_features: bool


class BillingOverviewResponse(BillingApiModel):
    plan: PlanSummary | None
    subscription: SubscriptionSummary | None
    credits: CreditSummary
    entitlements: EntitlementResponse


class CreditEntryResponse(BillingApiModel):
    id: UUID
    event_type: str
    amount: Decimal
    reason: str
    reference_type: str | None
    reference_id: str | None
    pricing_policy_version: str | None
    created_at: datetime


class InvoiceResponse(BillingApiModel):
    provider_invoice_ref: str
    status: str
    amount_due: Decimal
    currency: str
    hosted_invoice_url: str | None
    period_start: datetime | None
    period_end: datetime | None
    created_at: datetime


class WebhookResponse(BillingApiModel):
    status: str
