# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, MutableMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_OBJECT_DEFAULT


class UsageLedgerModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "usage_ledger"

    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("idempotency_operations.id", ondelete="RESTRICT")
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
    entry_key: Mapped[str] = mapped_column(String(128), nullable=False, server_default="primary")
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation_id",
            "metric",
            "entry_key",
            name="uq_usage_ledger_operation_metric_key",
        ),
        CheckConstraint("quantity >= 0", name="quantity"),
    )


class CostBudgetLimitModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "cost_budget_limits"

    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_limit: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    tolerance_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, server_default="0"
    )
    enforcement_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="hard"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('organization','project','agent_run','task','operation')",
            name="scope_type",
        ),
        CheckConstraint("amount_limit >= 0", name="amount"),
        CheckConstraint("tolerance_amount >= 0", name="tolerance"),
        CheckConstraint("enforcement_mode IN ('hard','approval')", name="mode"),
    )


class CostReservationModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "cost_reservations"

    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("idempotency_operations.id", ondelete="RESTRICT")
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
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="estimated"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation_id",
            "reservation_key",
            name="uq_cost_reservations_identity",
        ),
        CheckConstraint("estimated_amount >= 0", name="estimate"),
        CheckConstraint("actual_amount IS NULL OR actual_amount >= 0", name="actual"),
        CheckConstraint(
            "status IN ('active','committed','released','expired')", name="status"
        ),
    )


class QuotaLimitModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "quota_limits"

    scope_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="organization"
    )
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_limit: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('organization','project','agent_run')", name="scope_type"
        ),
        CheckConstraint("quantity_limit >= 0", name="quantity"),
    )


class QuotaLeaseModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "quota_leases"

    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("idempotency_operations.id", ondelete="RESTRICT")
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation_id",
            "metric",
            name="uq_quota_leases_identity",
        ),
        CheckConstraint("quantity > 0", name="quantity"),
    )


class CostBudgetChangeAuditModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "cost_budget_change_audit"

    budget_limit_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cost_budget_limits.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "action IN ('create','update','disable','enable')", name="action"
        ),
    )
