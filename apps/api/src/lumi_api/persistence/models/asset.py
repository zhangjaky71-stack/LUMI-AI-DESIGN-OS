from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, MutableTimestampMixin


class Asset(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
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
