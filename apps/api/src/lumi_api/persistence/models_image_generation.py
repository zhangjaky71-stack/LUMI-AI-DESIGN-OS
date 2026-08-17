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
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class ImageGenerationSpecModel(Base):
    __tablename__ = "image_generation_specs"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("semantic_hash ~ '^[0-9a-f]{64}$'", name="semantic_hash_format"),
        Index("ix_image_generation_specs_project", "organization_id", "project_id"),
    )


class ImageGenerationJobModel(Base):
    __tablename__ = "image_generation_jobs"

    generation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_variants: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_variants: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_per_variant: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    job_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("semantic_hash ~ '^[0-9a-f]{64}$'", name="semantic_hash_format"),
        CheckConstraint("requested_variants BETWEEN 1 AND 16", name="requested_variants_range"),
        CheckConstraint(
            "selected_variants BETWEEN 1 AND requested_variants",
            name="selected_variants_range",
        ),
        CheckConstraint("estimated_cost_per_variant >= 0", name="estimate_nonnegative"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','PROVIDER_PENDING','VALIDATING','COMPLETED',"
            "'PARTIAL','FAILED','CANCELLED')",
            name="status",
        ),
        Index(
            "uq_image_generation_job_operation",
            "organization_id",
            "operation_id",
            unique=True,
        ),
        Index(
            "ix_image_generation_jobs_org_status",
            "organization_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_image_generation_jobs_project_created",
            "organization_id",
            "project_id",
            "created_at",
        ),
    )


class ImageGenerationCandidateModel(Base):
    __tablename__ = "image_generation_candidates"

    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_generation_jobs.generation_id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_revision: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registry_snapshot_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    bucket: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    provenance_snapshot_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    cost_confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    routing_reason_codes_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    error_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("variant_index BETWEEN 1 AND 16", name="variant_index_range"),
        CheckConstraint(
            "status IN ('QUEUED','PROVIDER_PENDING','VALIDATING','READY','REJECTED',"
            "'FAILED','CANCELLED')",
            name="status",
        ),
        CheckConstraint("cost_amount IS NULL OR cost_amount >= 0", name="cost_nonnegative"),
        CheckConstraint(
            "checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum_format",
        ),
        Index(
            "uq_image_generation_candidate_variant",
            "generation_id",
            "variant_index",
            unique=True,
        ),
        Index(
            "uq_image_generation_candidate_operation",
            "organization_id",
            "variant_operation_id",
            unique=True,
        ),
        Index(
            "ix_image_generation_candidates_status",
            "organization_id",
            "status",
            "updated_at",
        ),
    )


class ImageGenerationPendingModel(Base):
    __tablename__ = "image_generation_pending"

    candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_generation_candidates.candidate_id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_generation_jobs.generation_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_request_id: Mapped[str] = mapped_column(String(300), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    poll_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    __table_args__ = (
        CheckConstraint("poll_attempts >= 0", name="poll_attempts_nonnegative"),
        Index(
            "ix_image_generation_pending_provider",
            "organization_id",
            "provider",
            "queued_at",
        ),
    )


class ImageGenerationCostProjectionModel(Base):
    __tablename__ = "image_generation_cost_projection"

    candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_generation_candidates.candidate_id", ondelete="CASCADE"),
        primary_key=True,
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_generation_jobs.generation_id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    monetary_owner: Mapped[str] = mapped_column(String(80), nullable=False)
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount >= 0", name="amount_nonnegative"),
        CheckConstraint(
            "monetary_owner = 'NODE27_MODEL_GATEWAY_SETTLEMENT'",
            name="monetary_owner",
        ),
        Index("ix_image_generation_cost_generation", "generation_id"),
    )
