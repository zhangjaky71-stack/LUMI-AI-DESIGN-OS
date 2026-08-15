# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base,
    CreatedAtMixin,
    MutableMixin,
    SoftDeleteMixin,
    TenantMixin,
    UUIDPrimaryKeyMixin,
)
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT
from .types import VectorType


class BrandModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin, SoftDeleteMixin):
    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )


class BrandPaletteModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "brand_palettes"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    colors_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )


class BrandFontModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "brand_fonts"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    family: Mapped[str] = mapped_column(String(200), nullable=False)
    source_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "assets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_brand_fonts_source_asset_id_assets",
        ),
        nullable=True,
    )
    usage_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )


class BrandLogoModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "brand_logos"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "assets.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_brand_logos_asset_id_assets",
        ),
        nullable=False,
    )
    variant: Mapped[str] = mapped_column(String(80), nullable=False, server_default="primary")


class BrandRuleModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "brand_rules"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint("severity IN ('hard','soft','advisory')", name="severity"),
    )


class ProjectModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin, SoftDeleteMixin):
    __tablename__ = "projects"

    workspace_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    brief_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    active_branch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "artifact_branches.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_projects_active_branch_id_artifact_branches",
        ),
        nullable=True,
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    __table_args__ = (
        CheckConstraint("status IN ('draft','active','paused','archived')", name="status"),
    )


class ProjectMemberModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "project_members"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        CheckConstraint("role IN ('admin','editor','viewer')", name="role"),
    )


class AssetModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin, SoftDeleteMixin):
    __tablename__ = "assets"

    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    semantic_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint("status IN ('pending','ready','failed','deleted')", name="status"),
    )


class AssetFileModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_files"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_asset_files_bucket_key"),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint("checksum_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
    )


class AssetPreviewModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_previews"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class AssetMetadataModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "asset_metadata"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        UniqueConstraint("asset_id", "namespace", name="uq_asset_metadata_asset_namespace"),
    )


class AssetEmbeddingModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_embeddings"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VectorType(), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "embedding_model",
            "embedding_version",
            "content_hash",
            name="uq_asset_embedding_version",
        ),
        CheckConstraint("dimensions > 0", name="dimensions_positive"),
    )


class AssetRightsModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "asset_rights"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    rights_level: Mapped[str] = mapped_column(String(32), nullable=False)
    commercial_use: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    attribution_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint(
            "rights_level IN ('unknown','owned','licensed','public_domain','restricted')",
            name="rights_level",
        ),
    )
