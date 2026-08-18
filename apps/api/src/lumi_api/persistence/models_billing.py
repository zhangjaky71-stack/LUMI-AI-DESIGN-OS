# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, MutableMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_OBJECT_DEFAULT


class BillingPlanModel(Base, UUIDPrimaryKeyMixin, MutableMixin):
    __tablename__ = "billing_plans"

    plan_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class BillingPlanVersionModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "billing_plan_versions"

    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing_plans.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    included_credits: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    postpaid_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    entitlements_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    pricing_policy_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_billing_plan_version"),)


class BillingAccountModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "billing_accounts"

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_customer_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="ACTIVE")

    __table_args__ = (
        UniqueConstraint("organization_id", "provider", name="uq_billing_account_provider"),
        UniqueConstraint("provider", "provider_customer_ref", name="uq_billing_provider_customer"),
    )


class BillingSubscriptionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "billing_subscriptions"

    billing_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    plan_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing_plan_versions.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_subscription_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_ref", name="uq_billing_provider_subscription"),
    )


class BillingCreditWalletModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "billing_credit_wallets"

    cached_balance: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False, server_default="0")
    allow_postpaid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (UniqueConstraint("organization_id", name="uq_billing_credit_wallet_org"),)


class BillingCreditLedgerModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "billing_credit_ledger"

    wallet_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing_credit_wallets.id", ondelete="RESTRICT"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pricing_policy_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "operation_id", name="uq_billing_credit_operation"),
    )


class BillingInvoiceRefModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "billing_invoice_refs"

    billing_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_invoice_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_invoice_ref", name="uq_billing_provider_invoice"),
    )


class BillingPaymentEventModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "billing_payment_events"

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="RECEIVED")
    rejection_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_billing_provider_event"),
    )
