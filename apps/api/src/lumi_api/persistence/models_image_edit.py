# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
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


class ImageEditSpecModel(Base):
    __tablename__ = "image_edit_specs"

    edit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
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
    source_artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_asset_version: Mapped[str] = mapped_column(String(160), nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "semantic_hash ~ '^[0-9a-f]{64}$'",
            name="semantic_hash_format",
        ),
        CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="source_checksum_format",
        ),
        Index(
            "uq_image_edit_spec_operation",
            "organization_id",
            "operation_id",
            unique=True,
        ),
        Index(
            "ix_image_edit_specs_project",
            "organization_id",
            "project_id",
            "created_at",
        ),
    )


class ImageEditJobModel(Base):
    __tablename__ = "image_edit_jobs"

    edit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_edit_specs.edit_id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    route: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_design_document_version_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    result_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    provenance_snapshot_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    validation_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(240), nullable=True)
    job_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "route IN ('STRUCTURAL_IR_EDIT','PIXEL_LOCAL_EDIT','REGENERATE_REGION',"
            "'FULL_IMAGE_EDIT','HYBRID')",
            name="route",
        ),
        CheckConstraint(
            "status IN ('PLANNED','QUEUED','AWAITING_MASK_APPROVAL',"
            "'AWAITING_CONFIRMATION','RUNNING','PROVIDER_PENDING','VALIDATING',"
            "'COMPLETED','REPAIR_REQUIRED','REJECTED','FAILED','CANCELLED')",
            name="status",
        ),
        CheckConstraint(
            "validation_decision IS NULL OR "
            "validation_decision IN ('PASS','REPAIR','REJECT')",
            name="validation_decision",
        ),
        Index(
            "ix_image_edit_jobs_status",
            "organization_id",
            "status",
            "updated_at",
        ),
    )


class ImageEditMaskModel(Base):
    __tablename__ = "image_edit_masks"

    edit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_edit_specs.edit_id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    mask_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_width: Mapped[int] = mapped_column(Integer, nullable=False)
    source_height: Mapped[int] = mapped_column(Integer, nullable=False)
    editable_rect_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    durable_ref: Mapped[str] = mapped_column(Text, nullable=False)
    preview_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    preview_approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source IN ('USER_BRUSH','DESIGN_IR','DETECTOR','AGENT_PROPOSED')",
            name="source",
        ),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum_format",
        ),
        CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="source_checksum_format",
        ),
        CheckConstraint(
            "source_width > 0 AND source_height > 0",
            name="source_dimensions",
        ),
        Index("ix_image_edit_masks_org", "organization_id"),
    )


class ImageEditPendingModel(Base):
    __tablename__ = "image_edit_pending"

    edit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_edit_specs.edit_id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_request_id: Mapped[str] = mapped_column(String(300), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    poll_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    __table_args__ = (
        CheckConstraint("poll_attempts >= 0", name="poll_attempts_nonnegative"),
        CheckConstraint(
            "length(provider_request_id) > 0",
            name="provider_request_nonempty",
        ),
        Index(
            "ix_image_edit_pending_provider",
            "organization_id",
            "provider",
            "queued_at",
        ),
    )


class ImageEditAuditModel(Base):
    __tablename__ = "image_edit_audits"

    edit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_edit_specs.edit_id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ImageEditCostProjectionModel(Base):
    __tablename__ = "image_edit_cost_projection"

    edit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("image_edit_specs.edit_id", ondelete="CASCADE"),
        primary_key=True,
    )
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    pricing_snapshot_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    monetary_owner: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        server_default="NODE27_MODEL_GATEWAY_SETTLEMENT",
    )
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount >= 0", name="amount_nonnegative"),
        CheckConstraint(
            "monetary_owner = 'NODE27_MODEL_GATEWAY_SETTLEMENT'",
            name="monetary_owner",
        ),
        Index("ix_image_edit_cost_operation", "operation_id"),
    )
