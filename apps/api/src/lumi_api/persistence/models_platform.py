# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, MutableMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_OBJECT_DEFAULT


class CostLedgerModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "cost_ledger"

    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("generations.id", ondelete="SET NULL"), nullable=True
    )
    operation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("idempotency_operations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reverses_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cost_ledger.id", ondelete="RESTRICT"), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_key: Mapped[str] = mapped_column(String(128), nullable=False, server_default="primary")
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provider_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_provider_request_id: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unknown")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="final")
    cost_basis: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="provider_cost"
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default="runtime")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('estimate','reservation','actual_cost','reversal','adjustment')",
            name="entry_type",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint(
            "(entry_type IN ('actual_cost','estimate','reservation') "
            "AND reverses_entry_id IS NULL) OR "
            "(entry_type IN ('reversal','adjustment') AND reverses_entry_id IS NOT NULL)",
            name="reversal_semantics",
        ),
        CheckConstraint(
            "confidence IN ('exact','estimated','unknown')", name="confidence"
        ),
        CheckConstraint(
            "status IN ('unknown','estimated','partial','final','reconciled')",
            name="status",
        ),
        CheckConstraint(
            "cost_basis IN ('provider_cost','customer_charge')", name="cost_basis"
        ),
        UniqueConstraint(
            "organization_id",
            "operation_id",
            "entry_type",
            "entry_key",
            name="uq_cost_ledger_operation_entry_key",
        ),
    )


class UsageCounterModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "usage_counters"

    period_key: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(30, 10), nullable=False, server_default="0"
    )
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "period_key", "metric_key", name="uq_usage_counter_scope"
        ),
    )


class OutboxEventModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_publish_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class InboxEventModel(Base, TenantMixin, CreatedAtMixin):
    __tablename__ = "inbox_events"

    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(160), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEventModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(160), nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
