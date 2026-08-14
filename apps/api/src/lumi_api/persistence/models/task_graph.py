from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin


class TaskGraphInstance(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "task_graph_instances"
    __table_args__ = (
        CheckConstraint("task_count > 0", name="task_count"),
        CheckConstraint("state_version > 0", name="state_version"),
        CheckConstraint(
            "completed_count >= 0 AND completed_count <= task_count",
            name="completed_count",
        ),
        Index("ix_task_graph_instances_org_status", "organization_id", "status"),
        Index("ix_task_graph_instances_agent_run", "agent_run_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_provenance_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    task_graph_template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_budget_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    task_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskAttemptRecord(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_number", name="task_number"),
        CheckConstraint("attempt_number > 0", name="number"),
        CheckConstraint("cost_amount_usd IS NULL OR cost_amount_usd >= 0", name="cost"),
        Index("ix_task_attempts_graph_created", "task_graph_id", "created_at"),
        Index("ix_task_attempts_logical_operation", "logical_operation_key", "attempt_number"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    task_graph_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("task_graph_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    logical_operation_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(128))
    result_ref: Mapped[str | None] = mapped_column(String(1024))
    cost_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
