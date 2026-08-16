from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class BillingPlanVersion(Base):
    __tablename__ = "billing_plan_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("price_microusd >= 0", name="price_nonnegative"),
        CheckConstraint(
            "billing_interval IN ('MONTH','YEAR')",
            name="interval_valid",
        ),
        CheckConstraint("monthly_credit_grant >= 0", name="credit_grant_nonnegative"),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="status_valid"),
        UniqueConstraint(
            "plan_id",
            "version",
            name="uq_billing_plan_versions_plan_version",
        ),
    )

    plan_version_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    price_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(10), nullable=False)
    monthly_credit_grant: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entitlements: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BillingAccount(Base):
    __tablename__ = "billing_accounts"
    __table_args__ = (
        UniqueConstraint(
            "payment_provider",
            "payment_customer_ref",
            name="uq_billing_accounts_provider_customer",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    payment_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_customer_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"

    subscription_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    plan_version_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("billing_plan_versions.plan_version_id"),
        nullable=False,
    )
    payment_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_subscription_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint(
            "state IN ("
            "'TRIALING','ACTIVE','PAST_DUE','CANCEL_AT_PERIOD_END','CANCELLED','INCOMPLETE'"
            ")",
            name="state_valid",
        ),
        nullable=False,
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BillingPaymentEvent(Base):
    __tablename__ = "billing_payment_events"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    provider_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PAID','OPEN','FAILED','VOID')",
            name="status_valid",
        ),
        CheckConstraint("amount_due_microusd >= 0", name="amount_nonnegative"),
        UniqueConstraint(
            "provider",
            "provider_invoice_ref",
            name="uq_billing_invoices_provider_invoice",
        ),
        Index(
            "ix_billing_invoices_org_created",
            "organization_id",
            text("created_at DESC"),
        ),
    )

    invoice_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_invoice_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_version_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("billing_plan_versions.plan_version_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_due_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BillingCreditLedger(Base):
    __tablename__ = "billing_credit_ledger"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ("
            "'GRANT','CONSUME','REFUND','EXPIRE','ADJUSTMENT','REVERSAL'"
            ")",
            name="entry_type_valid",
        ),
        CheckConstraint("delta_credits <> 0", name="delta_nonzero"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_billing_credit_ledger_org_idempotency",
        ),
        Index(
            "ix_billing_credit_ledger_org_created",
            "organization_id",
            text("created_at DESC"),
        ),
    )

    entry_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    delta_credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    pricing_policy_version: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    usage_record_id: Mapped[str | None] = mapped_column(String(255))
    reverses_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("billing_credit_ledger.entry_id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
