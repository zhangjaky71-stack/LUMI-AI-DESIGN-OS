from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, MutableTimestampMixin


class Asset(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading','scanning','ready','rejected')",
            name="status",
        ),
        Index("ix_assets_org_created", "organization_id", "created_at"),
        Index("ix_assets_project_created", "project_id", "created_at"),
        Index("ix_assets_org_kind", "organization_id", "kind"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="upload")
    original_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploading")
    rejection_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetFile(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_files"
    __table_args__ = (
        UniqueConstraint("asset_id", "variant", name="asset_file_variant"),
        UniqueConstraint("organization_id", "bucket", "object_key", name="asset_object_key"),
        Index("ix_asset_files_org_asset", "organization_id", "asset_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant: Mapped[str] = mapped_column(String(64), nullable=False, default="original")
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AssetUploadSession(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_upload_sessions"
    __table_args__ = (
        UniqueConstraint("file_id", name="uq_asset_upload_sessions_file"),
        UniqueConstraint(
            "organization_id",
            "bucket",
            "object_key",
            name="uq_asset_upload_sessions_object",
        ),
        CheckConstraint(
            "status IN ('pending','completed','expired','aborted','rejected')",
            name="status",
        ),
        CheckConstraint("upload_mode IN ('single','multipart')", name="mode"),
        CheckConstraint(
            "declared_size > 0 AND (verified_size IS NULL OR verified_size >= 0)",
            name="size",
        ),
        CheckConstraint(
            "expected_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum",
        ),
        Index(
            "ix_asset_upload_sessions_org_status_expiry",
            "organization_id",
            "status",
            "expires_at",
        ),
        Index("ix_asset_upload_sessions_project_created", "project_id", "created_at"),
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
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    upload_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    multipart_upload_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    declared_mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_checksum_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verification_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AssetValidationRun(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_validation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','rejected','error')",
            name="status",
        ),
        CheckConstraint(
            "scanner_status IS NULL OR scanner_status IN ('CLEAN','INFECTED','SCAN_UNAVAILABLE','ERROR')",
            name="scanner",
        ),
        CheckConstraint(
            "full_checksum_sha256 IS NULL OR full_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum",
        ),
        Index(
            "ix_asset_validation_runs_org_asset",
            "organization_id",
            "asset_id",
            "created_at",
        ),
        Index("ix_asset_validation_runs_status_created", "status", "created_at"),
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
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scanner_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sniffed_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_checksum_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetPreview(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_previews"
    __table_args__ = (
        UniqueConstraint("asset_id", "preview_kind", name="asset_preview_kind"),
        Index("ix_asset_previews_org_asset", "organization_id", "asset_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("asset_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    preview_kind: Mapped[str] = mapped_column(String(64), nullable=False)


class AssetMetadata(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_metadata"
    __table_args__ = (
        UniqueConstraint("asset_id", "namespace", name="asset_metadata_namespace"),
        Index("ix_asset_metadata_org_asset", "organization_id", "asset_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AssetEmbedding(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "embedding_model",
            "embedding_version",
            "content_hash",
            name="asset_embedding_identity",
        ),
        Index("ix_asset_embeddings_org_asset", "organization_id", "asset_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)


class AssetRights(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "asset_rights"
    __table_args__ = (
        UniqueConstraint("asset_id", name="asset_rights_asset"),
        CheckConstraint(
            "source_type IN ('USER_UPLOAD','GENERATED','LICENSED','PUBLIC_DOMAIN','THIRD_PARTY','UNKNOWN')",
            name="source_type",
        ),
        CheckConstraint(
            "license_type IN ('OWNED','COMMERCIAL_LICENSE','NONCOMMERCIAL','PUBLIC_DOMAIN','CC_BY','CC_BY_SA','UNKNOWN')",
            name="license_type",
        ),
        CheckConstraint("commercial_use IN ('ALLOWED','DENIED','UNKNOWN')", name="commercial_use"),
        CheckConstraint("redistribution IN ('ALLOWED','DENIED','UNKNOWN')", name="redistribution"),
        CheckConstraint("training_use IN ('ALLOWED','DENIED','UNKNOWN')", name="training_use"),
        CheckConstraint(
            "review_status IN ('UNREVIEWED','ASSERTED','VERIFIED','RESTRICTED')",
            name="review_status",
        ),
        Index("ix_asset_rights_org_asset", "organization_id", "asset_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    attribution_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    owner_assertion: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_type: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    commercial_use: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    redistribution: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    training_use: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNREVIEWED")
