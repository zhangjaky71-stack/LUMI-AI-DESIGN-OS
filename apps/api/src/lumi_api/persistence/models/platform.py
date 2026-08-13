from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin, MutableTimestampMixin


class CostLedger(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "cost_ledger"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="cost_ledger_currency_check"),
        Index("ix_cost_ledger_org_created", "organization_id", "created_at"),
        Index("ix_cost_ledger_project_created", "project_id", "created_at"),
        Index("ix_cost_ledger_generation", "generation_id"),
        Index("ix_cost_ledger_provider_request", "provider_request_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provider_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    reverses_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cost_ledger.id", ondelete="RESTRICT"),
        nullable=True,
    )
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class UsageCounter(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_key",
            "metric",
            name="uq_usage_counters_identity",
        ),
        Index("ix_usage_counters_org_period", "organization_id", "period_key"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)


class IdempotencyOperation(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "idempotency_operations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_idempotency_operations_org_key",
        ),
        Index("ix_idempotency_operations_status_created", "status", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OutboxEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("schema_version > 0", name="outbox_events_schema_version_check"),
        CheckConstraint("publish_attempts >= 0", name="outbox_events_publish_attempts_check"),
        Index("ix_outbox_pending", "published_at", "created_at"),
        Index("ix_outbox_org_created", "organization_id", "created_at"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_name: Mapped[str] = mapped_column(String(150), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InboxEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "inbox_events"
    __table_args__ = (
        UniqueConstraint(
            "consumer",
            "event_id",
            name="uq_inbox_events_consumer_event",
        ),
        Index("ix_inbox_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    consumer: Mapped[str] = mapped_column(String(150), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
        Index("ix_audit_events_actor_created", "actor_id", "created_at"),
        Index("ix_audit_events_target", "target_type", "target_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(150), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
