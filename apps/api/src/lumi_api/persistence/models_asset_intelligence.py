# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class AssetIntelligenceIndexCounterModel(Base):
    __tablename__ = "asset_intelligence_index_counters"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    next_version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("next_version > 0", name="next_version_positive"),)


class AssetIntelligenceIndexModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_intelligence_indexes"

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_model_key: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_revision_key: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_space_id: Mapped[str] = mapped_column(String(320), nullable=False)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    coverage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "version_number", name="uq_asset_intelligence_index_version"
        ),
        CheckConstraint("version_number > 0", name="version_positive"),
        CheckConstraint("embedding_dimensions > 0", name="embedding_dimensions_positive"),
        CheckConstraint("coverage_count >= 0", name="coverage_nonnegative"),
        CheckConstraint(
            "state IN ('BUILDING','READY','ACTIVE','RETIRED','FAILED')",
            name="state",
        ),
        Index(
            "uq_asset_intelligence_one_active_per_org",
            "organization_id",
            unique=True,
            postgresql_where=text("state='ACTIVE'"),
        ),
        Index(
            "ix_asset_intelligence_indexes_org_state",
            "organization_id",
            "state",
            "version_number",
        ),
    )


class AssetIntelligenceAnalysisModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_intelligence_analysis"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    asset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    index_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("asset_intelligence_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    media_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    rights_level: Mapped[str] = mapped_column(String(32), nullable=False)
    commercial_use: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    training_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    permission_tags_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    preview_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    ocr_spans_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    regions_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    semantic_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_tags_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    embedding_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("asset_embeddings.id", ondelete="SET NULL"), nullable=True
    )
    perceptual_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    local_signature_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    color_signature_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    brand_region_signature_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    analyzer_version: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_model_key: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_revision_key: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(80), nullable=False)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_refs_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "asset_id", "index_id",
            name="uq_asset_intelligence_analysis_asset_index",
        ),
        CheckConstraint("asset_version ~ '^[0-9a-f]{64}$'", name="asset_version_format"),
        CheckConstraint("checksum_sha256 ~ '^[0-9a-f]{64}$'", name="checksum_format"),
        CheckConstraint(
            "state IN ('READY','STALE','DELETING','DELETED','FAILED')",
            name="state",
        ),
        CheckConstraint(
            "rights_level IN ('unknown','owned','licensed','public_domain','restricted')",
            name="rights_level",
        ),
        Index(
            "ix_asset_intelligence_analysis_scope",
            "organization_id",
            "index_id",
            "state",
            "project_id",
            "brand_id",
            "rights_level",
        ),
        Index(
            "ix_asset_intelligence_analysis_asset",
            "organization_id",
            "asset_id",
            "index_id",
        ),
        Index(
            "ix_asset_intelligence_analysis_tags_gin",
            "visual_tags_json",
            postgresql_using="gin",
        ),
    )


class AssetIntelligenceUsageSignalModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "asset_intelligence_usage_signals"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    signal: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    training_authorization_granted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("signal IN ('SELECTED','APPROVED','REJECTED')", name="signal"),
        CheckConstraint(
            "training_authorization_granted = false",
            name="training_authorization_forbidden",
        ),
        Index(
            "ix_asset_intelligence_usage_asset_time",
            "organization_id",
            "asset_id",
            "occurred_at",
        ),
    )
