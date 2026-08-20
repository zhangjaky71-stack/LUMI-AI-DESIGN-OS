from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, MutableTimestampMixin


class VideoGenerationJob(MutableTimestampMixin, Base):
    __tablename__ = "video_generation_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation_id",
            name="video_generation_job_operation_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "task_id",
            name="video_generation_job_task_identity",
        ),
        Index("ix_video_generation_jobs_org_project", "organization_id", "project_id"),
        Index("ix_video_generation_jobs_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
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
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storyboard_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    actual_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    spec_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    job_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    final_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VideoProviderJob(MutableTimestampMixin, Base):
    __tablename__ = "video_provider_jobs"
    __table_args__ = (
        UniqueConstraint(
            "video_job_id",
            "shot_id",
            "paid_operation_id",
            name="video_provider_job_paid_attempt_identity",
        ),
        Index("ix_video_provider_jobs_org_job", "organization_id", "video_job_id"),
        Index(
            "uq_video_provider_jobs_active_shot",
            "video_job_id",
            "shot_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    video_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("video_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    shot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    paid_operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempt_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
