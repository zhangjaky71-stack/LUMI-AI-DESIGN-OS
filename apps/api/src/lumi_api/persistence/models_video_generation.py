# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VideoGenerationSpecModel(Base):
    __tablename__ = "video_generation_specs"

    video_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
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
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "semantic_hash ~ '^[0-9a-f]{64}$'",
            name="video_generation_semantic_hash",
        ),
        CheckConstraint(
            "mode IN ('TEXT_TO_VIDEO','IMAGE_TO_VIDEO','KEYFRAME_TO_VIDEO',"
            "'PRODUCT_MOTION','LOOP')",
            name="video_generation_mode",
        ),
        CheckConstraint(
            "width > 0 AND height > 0 AND width <= 8192 AND height <= 8192 "
            "AND fps > 0 AND fps <= 120",
            name="video_generation_dimensions",
        ),
        CheckConstraint(
            "budget_limit_usd IS NULL OR budget_limit_usd >= 0",
            name="video_generation_budget",
        ),
        Index(
            "uq_video_generation_operation",
            "organization_id",
            "operation_id",
            unique=True,
        ),
        Index(
            "ix_video_generation_specs_project",
            "organization_id",
            "project_id",
            "created_at",
        ),
    )


class VideoGenerationJobModel(Base):
    __tablename__ = "video_generation_jobs"

    video_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("video_generation_specs.video_job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    final_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    final_durable_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    job_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(240), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNED','WAITING_EXTERNAL','VALIDATING','COMPOSING',"
            "'COMPLETED','CANCEL_REQUESTED','CANCELLED','FAILED')",
            name="video_generation_job_status",
        ),
        Index(
            "ix_video_generation_jobs_status",
            "organization_id",
            "status",
            "updated_at",
        ),
    )


class VideoGenerationShotModel(Base):
    __tablename__ = "video_generation_shots"

    video_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("video_generation_specs.video_job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    shot_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    shot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(240), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "ordinal >= 0 AND retry_ordinal >= 0",
            name="video_generation_shot_ordinal",
        ),
        CheckConstraint(
            "status IN ('PLANNED','WAITING_EXTERNAL','READY','FAILED','CANCELLED')",
            name="video_generation_shot_status",
        ),
        Index(
            "uq_video_generation_shot_operation",
            "organization_id",
            "paid_operation_id",
            unique=True,
        ),
        Index(
            "ix_video_generation_shots_status",
            "organization_id",
            "status",
            "updated_at",
        ),
    )


class VideoProviderJobModel(Base):
    __tablename__ = "video_provider_jobs"

    video_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shot_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    retry_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_request_id: Mapped[str] = mapped_column(String(300), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    poll_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    terminal_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["video_job_id", "shot_id"],
            [
                "video_generation_shots.video_job_id",
                "video_generation_shots.shot_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "poll_attempts >= 0",
            name="video_provider_poll_attempts",
        ),
        CheckConstraint(
            "length(provider_request_id) > 0",
            name="video_provider_request_id",
        ),
        CheckConstraint(
            "terminal_status IS NULL OR terminal_status IN "
            "('COMPLETED','FAILED','CANCELLED')",
            name="video_provider_terminal_status",
        ),
        Index(
            "ix_video_provider_jobs_pending",
            "organization_id",
            "queued_at",
            postgresql_where=text("terminal_status IS NULL"),
        ),
    )


class VideoGenerationClipModel(Base):
    __tablename__ = "video_generation_clips"

    video_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shot_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    retry_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    durable_ref: Mapped[str] = mapped_column(Text, nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    decodable_frames: Mapped[int] = mapped_column(Integer, nullable=False)
    black_frame_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    clip_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["video_job_id", "shot_id"],
            [
                "video_generation_shots.video_job_id",
                "video_generation_shots.shot_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="video_clip_checksum",
        ),
        CheckConstraint(
            "width > 0 AND height > 0 AND duration_seconds > 0 "
            "AND decodable_frames > 0 AND black_frame_ratio >= 0 "
            "AND black_frame_ratio <= 1 AND size_bytes > 0",
            name="video_clip_probe",
        ),
        CheckConstraint(
            "storage_key NOT LIKE 'http%' "
            "AND storage_key NOT LIKE '%X-Amz-Signature%'",
            name="video_clip_storage_key",
        ),
    )


class VideoGenerationCostProjectionModel(Base):
    __tablename__ = "video_generation_cost_projection"

    video_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shot_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    retry_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    monetary_owner: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        server_default="NODE27_MODEL_GATEWAY_SETTLEMENT",
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "amount_usd IS NULL OR amount_usd >= 0",
            name="video_cost_amount",
        ),
        CheckConstraint(
            "monetary_owner = 'NODE27_MODEL_GATEWAY_SETTLEMENT'",
            name="video_cost_owner",
        ),
        Index("ix_video_cost_operation", "operation_id"),
    )


class VideoWebhookDedupeModel(Base):
    __tablename__ = "video_webhook_dedupe"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(120), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(300), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
