# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProviderHealthSummaryModel(Base):
    __tablename__ = "provider_health_summaries"
    __table_args__ = (
        CheckConstraint(
            "state IN ('unknown','healthy','degraded','open_circuit','recovering','disabled')",
            name="ck_provider_health_summary_state",
        ),
        CheckConstraint(
            "score BETWEEN 0 AND 100",
            name="ck_provider_health_summary_score",
        ),
        CheckConstraint(
            "sample_count >= 0",
            name="ck_provider_health_summary_sample_count",
        ),
        CheckConstraint(
            "success_rate BETWEEN 0 AND 1",
            name="ck_provider_health_summary_success_rate",
        ),
        CheckConstraint(
            "failure_rate BETWEEN 0 AND 1",
            name="ck_provider_health_summary_failure_rate",
        ),
        CheckConstraint(
            "rate_limit_rate BETWEEN 0 AND 1",
            name="ck_provider_health_summary_rate_limit_rate",
        ),
        CheckConstraint(
            "timeout_rate BETWEEN 0 AND 1",
            name="ck_provider_health_summary_timeout_rate",
        ),
        CheckConstraint(
            "latency_p50_ms IS NULL OR latency_p50_ms >= 0",
            name="ck_provider_health_summary_latency_p50",
        ),
        CheckConstraint(
            "latency_p95_ms IS NULL OR latency_p95_ms >= 0",
            name="ck_provider_health_summary_latency_p95",
        ),
        CheckConstraint(
            "queue_completion_p95_ms IS NULL OR queue_completion_p95_ms >= 0",
            name="ck_provider_health_summary_queue_p95",
        ),
        CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_provider_health_summary_consecutive",
        ),
        CheckConstraint(
            "capability IS NULL OR model IS NOT NULL",
            name="ck_provider_health_summary_capability_scope",
        ),
        Index(
            "ix_provider_health_summary_scope_observed",
            "provider",
            "model",
            "capability",
            "observed_at",
        ),
        Index(
            "ix_provider_health_summary_state_observed",
            "state",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    model: Mapped[str | None] = mapped_column(String(255))
    capability: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    success_rate: Mapped[Decimal] = mapped_column(
        Numeric(7, 6),
        nullable=False,
    )
    failure_rate: Mapped[Decimal] = mapped_column(
        Numeric(7, 6),
        nullable=False,
    )
    rate_limit_rate: Mapped[Decimal] = mapped_column(
        Numeric(7, 6),
        nullable=False,
    )
    timeout_rate: Mapped[Decimal] = mapped_column(
        Numeric(7, 6),
        nullable=False,
    )
    latency_p50_ms: Mapped[int | None] = mapped_column(Integer)
    latency_p95_ms: Mapped[int | None] = mapped_column(Integer)
    queue_completion_p95_ms: Mapped[int | None] = mapped_column(
        Integer
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_instance: Mapped[str | None] = mapped_column(
        String(255)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProviderHealthOverrideAuditModel(Base):
    __tablename__ = "provider_health_override_audit"
    __table_args__ = (
        CheckConstraint(
            "action IN ('force_disabled','force_degraded','clear_override','clear_breaker')",
            name="ck_provider_health_audit_action",
        ),
        CheckConstraint(
            "length(btrim(actor_id)) > 0",
            name="ck_provider_health_audit_actor",
        ),
        CheckConstraint(
            "length(btrim(reason)) > 0",
            name="ck_provider_health_audit_reason",
        ),
        CheckConstraint(
            "capability IS NULL OR model IS NOT NULL",
            name="ck_provider_health_audit_capability_scope",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > observed_at",
            name="ck_provider_health_audit_expiry",
        ),
        Index(
            "ix_provider_health_audit_scope_observed",
            "provider",
            "model",
            "capability",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    model: Mapped[str | None] = mapped_column(String(255))
    capability: Mapped[str | None] = mapped_column(String(128))
    actor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
