from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin, MutableTimestampMixin


class AgentRun(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_org_project", "organization_id", "project_id"),
        Index("ix_agent_runs_project_created", "project_id", "created_at"),
        Index("ix_agent_runs_project_status", "project_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_config_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunStep(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "sequence_number", name="agent_run_step_sequence"),
        Index("ix_agent_run_steps_org_run", "organization_id", "agent_run_id"),
        Index("ix_agent_run_steps_run_created", "agent_run_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    trace_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Task(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("state_version > 0", name="state_version"),
        CheckConstraint(
            "progress_total > 0 AND progress_current >= 0 AND progress_current <= progress_total",
            name="progress",
        ),
        CheckConstraint("dynamic_depth >= 0 AND dynamic_depth <= 4", name="dynamic_depth"),
        CheckConstraint(
            "dynamic_child_limit >= 0 AND dynamic_child_limit <= 32",
            name="dynamic_child_limit",
        ),
        CheckConstraint(
            "concurrency_limit IS NULL OR (concurrency_limit >= 1 AND concurrency_limit <= 32)",
            name="concurrency_limit",
        ),
        CheckConstraint(
            "budget_limit_usd IS NULL OR budget_limit_usd > 0",
            name="budget_limit_usd",
        ),
        Index("ix_tasks_org_project", "organization_id", "project_id"),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_agent_run_created", "agent_run_id", "created_at"),
        Index("ix_tasks_schedule", "status", "priority", "created_at"),
        Index(
            "uq_tasks_graph_task_key",
            "task_graph_id",
            "task_key",
            unique=True,
            postgresql_where=text("task_graph_id IS NOT NULL AND task_key IS NOT NULL"),
        ),
        Index(
            "ix_tasks_ready_claim",
            "task_graph_id",
            "status",
            "retry_not_before",
            "priority",
        ),
        Index("ix_tasks_lease_reap", "status", "lease_expires_at"),
        Index("ix_tasks_concurrency_group", "task_graph_id", "concurrency_group", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_graph_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("task_graph_instances.id", ondelete="CASCADE"),
        nullable=True,
    )
    recipe_step_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    owner_agent_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition_expression: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    budget_reserved: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    budget_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dynamic_depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dynamic_child_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    concurrency_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    concurrency_limit: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskDependency(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint("task_id <> depends_on_task_id", name="task_dependency_no_self_loop"),
        UniqueConstraint("task_id", "depends_on_task_id", name="task_dependency_identity"),
        Index("ix_task_dependencies_org_task", "organization_id", "task_id"),
        Index("ix_task_dependencies_depends_on", "depends_on_task_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    depends_on_task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )


class Approval(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_org_project", "organization_id", "project_id"),
        Index("ix_approvals_status_created", "status", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    requested_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    decided_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Generation(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "generations"
    __table_args__ = (
        Index("ix_generations_org_project", "organization_id", "project_id"),
        Index("ix_generations_task_created", "task_id", "created_at"),
        Index("ix_generations_agent_run_created", "agent_run_id", "created_at"),
        Index("ix_generations_status_created", "status", "created_at"),
        Index(
            "uq_generations_org_operation",
            "organization_id",
            "operation_id",
            unique=True,
            postgresql_where=text("operation_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
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
    operation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ProviderRequest(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "provider_requests"
    __table_args__ = (
        UniqueConstraint("provider", "provider_request_id", name="provider_request_native_id"),
        Index("ix_provider_requests_org_generation", "organization_id", "generation_id"),
        Index("ix_provider_requests_native", "provider_request_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_retryable: Mapped[bool | None] = mapped_column(nullable=True)
