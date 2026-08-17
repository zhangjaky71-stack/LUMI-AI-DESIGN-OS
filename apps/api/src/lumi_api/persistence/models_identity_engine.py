# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class IdentityReferenceSetModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "identity_reference_sets"

    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=True
    )
    identity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    privacy_authorized: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    __table_args__ = (
        CheckConstraint(
            "identity_type IN ('PRODUCT','LOGO','CHARACTER','FACE','STYLE_REFERENCE')",
            name="identity_type",
        ),
        CheckConstraint(
            "identity_type <> 'FACE' OR "
            "(project_id IS NOT NULL AND brand_id IS NULL AND privacy_authorized)",
            name="face_project_privacy_scope",
        ),
    )


class IdentityVersionCounterModel(Base, TenantMixin):
    __tablename__ = "identity_version_counters"

    identity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    next_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    __table_args__ = (
        CheckConstraint("next_version >= 2", name="next_version_minimum"),
    )


class IdentityReferenceSetVersionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "identity_reference_set_versions"

    identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_reference_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_asset_ids_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    reference_views_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    threshold_profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("identity_id", "version_number", name="uq_identity_ref_version"),
        CheckConstraint("version_number > 0", name="version_positive"),
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_format"),
    )


class IdentityValidationRecordModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "identity_validation_records"

    identity_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_reference_set_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    node_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_score: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    threshold_profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signal_scores_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    region_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence_refs_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    failure_codes_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    provider_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "status IN ('PASS','WARN','BLOCKED','REVIEW_REQUIRED','VALIDATION_UNAVAILABLE')",
            name="status",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class IdentityCalibrationReportModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "identity_calibration_reports"

    identity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_threshold: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    target_precision: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "identity_type", "profile_key", "version_number",
            name="uq_identity_calibration_profile_version",
        ),
        CheckConstraint(
            "selected_threshold >= 0 AND selected_threshold <= 100",
            name="threshold_range",
        ),
        CheckConstraint("target_precision >= 0 AND target_precision <= 1", name="precision_range"),
        CheckConstraint("sample_count > 0", name="sample_count_positive"),
    )
