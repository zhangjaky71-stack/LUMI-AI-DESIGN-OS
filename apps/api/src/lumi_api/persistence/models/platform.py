from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin, MutableTimestampMixin


class CostLedger(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "cost_ledger"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_check"),
        CheckConstraint(
            "confidence IN ('exact','estimated','unknown')",
            name="confidence",
        ),
        CheckConstraint(
            "cost_basis IN ('provider_cost','customer_charge')",
            name="cost_basis",
        ),
        CheckConstraint("length(entry_key) BETWEEN 1 AND 128", name="entry_key"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_nonnegative"),
        UniqueConstraint(
            "operation_id",
            "entry_type",
            "entry_key",
            name="uq_cost_ledger_operation_entry_key",
        ),
        Index("ix_cost_ledger_org_created", "organization_id", "created_at"),
        Index("ix_cost_ledger_project_created", "project_id", "created_at"),
        Index("ix_cost_ledger_generation", "generation_id"),
        Index("ix_cost_ledger_provider_request", "provider_request_id"),
        Index("ix_cost_ledger_operation", "operation_id"),
        Index("ix_cost_ledger_org_occurred", "organization_id", "occurred_at"),
        Index(
            "ix_cost_ledger_org_type_occurred",
            "organization_id",
            "entry_type",
            "occurred_at",
        ),
        Index(
            "ix_cost_ledger_pricing_snapshot",
            "pricing_snapshot_id",
            postgresql_where=text("pricing_snapshot_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("idempotency_operations.id", ondelete="RESTRICT"),
        nullable=True,
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
    entry_key: Mapped[str] = mapped_column(String(128), nullable=False, default="primary")
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_provider_request_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    cost_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="provider_cost")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="runtime")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CostBudgetLimit(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "cost_budget_limits"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('organization','project','agent_run','task','operation')",
            name="scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'organization' AND scope_id IS NULL) OR "
            "(scope_type <> 'organization' AND scope_id IS NOT NULL)",
            name="scope_identity",
        ),
        CheckConstraint("length(period_key) BETWEEN 1 AND 32", name="period_key"),
        CheckConstraint("amount_limit >= 0", name="amount"),
        CheckConstraint("tolerance_amount >= 0", name="tolerance"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        Index(
            "uq_cost_budget_limits_identity",
            "organization_id",
            "scope_type",
            text("COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "period_key",
            "currency",
            unique=True,
        ),
        Index(
            "ix_cost_budget_limits_org_scope",
            "organization_id",
            "scope_type",
            "scope_id",
            "period_key",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_limit: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    tolerance_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CostReservation(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "cost_reservations"
    __table_args__ = (
        UniqueConstraint("operation_id", "reservation_key", name="uq_cost_reservations_identity"),
        CheckConstraint("estimated_amount >= 0", name="estimate"),
        CheckConstraint("actual_amount IS NULL OR actual_amount >= 0", name="actual"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("confidence IN ('exact','estimated','unknown')", name="confidence"),
        CheckConstraint(
            "status IN ('active','committed','released','expired')",
            name="status",
        ),
        Index("ix_cost_reservations_org_active", "organization_id", "status", "expires_at"),
        Index(
            "ix_cost_reservations_project_active",
            "project_id",
            "status",
            "expires_at",
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index(
            "ix_cost_reservations_agent_run_active",
            "agent_run_id",
            "status",
            "expires_at",
            postgresql_where=text("agent_run_id IS NOT NULL"),
        ),
        Index(
            "ix_cost_reservations_task_active",
            "task_id",
            "status",
            "expires_at",
            postgresql_where=text("task_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("idempotency_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    reservation_key: Mapped[str] = mapped_column(String(512), nullable=False)
    estimated_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="estimated")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class UsageLedger(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        UniqueConstraint(
            "operation_id", "metric", "entry_key", name="uq_usage_ledger_operation_metric_key"
        ),
        CheckConstraint("quantity >= 0", name="quantity"),
        CheckConstraint("length(metric) BETWEEN 1 AND 100", name="metric"),
        CheckConstraint("length(entry_key) BETWEEN 1 AND 128", name="entry_key"),
        Index("ix_usage_ledger_org_occurred", "organization_id", "occurred_at"),
        Index(
            "ix_usage_ledger_project_occurred",
            "project_id",
            "occurred_at",
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index("ix_usage_ledger_metric_occurred", "organization_id", "metric", "occurred_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("idempotency_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cost_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cost_ledger.id", ondelete="RESTRICT"), nullable=True
    )
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
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_provider_request_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    entry_key: Mapped[str] = mapped_column(String(128), nullable=False, default="primary")
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class QuotaLimit(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "quota_limits"
    __table_args__ = (
        CheckConstraint("scope_type IN ('organization','project','agent_run')", name="scope_type"),
        CheckConstraint(
            "(scope_type = 'organization' AND scope_id IS NULL) OR "
            "(scope_type <> 'organization' AND scope_id IS NOT NULL)",
            name="scope_identity",
        ),
        CheckConstraint("quantity_limit >= 0", name="quantity"),
        CheckConstraint("length(metric) BETWEEN 1 AND 100", name="metric"),
        CheckConstraint("length(period_key) BETWEEN 1 AND 32", name="period_key"),
        Index(
            "uq_quota_limits_identity",
            "organization_id",
            "scope_type",
            text("COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "metric",
            "period_key",
            unique=True,
        ),
        Index("ix_quota_limits_org_metric", "organization_id", "metric", "period_key"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="organization")
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_limit: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class QuotaLeaseModel(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "quota_leases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "operation_id", "metric", name="uq_quota_leases_identity"
        ),
        CheckConstraint("quantity > 0", name="quantity"),
        Index(
            "ix_quota_leases_active",
            "organization_id",
            "metric",
            "expires_at",
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("idempotency_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
            "operation_type",
            "idempotency_key",
            name="uq_idempotency_operations_identity",
        ),
        CheckConstraint(
            "status IN ('new','in_progress','succeeded','failed_retryable',"
            "'failed_final','ambiguous')",
            name="status",
        ),
        CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 100 AND 599",
            name="response_status",
        ),
        CheckConstraint(
            "error_category IS NULL OR error_category IN ('transient','permanent','ambiguous')",
            name="error_category",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        Index("ix_idempotency_operations_status_created", "status", "created_at"),
        Index("ix_idempotency_operations_lease", "status", "lease_expires_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ambiguity_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)


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
