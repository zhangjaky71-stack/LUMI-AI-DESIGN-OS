from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin, MutableTimestampMixin


class Brand(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (Index("ix_brands_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    tone_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class BrandPalette(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "brand_palettes"
    __table_args__ = (
        UniqueConstraint("brand_id", "name", name="brand_palette_name"),
        Index("ix_brand_palettes_org_brand", "organization_id", "brand_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    colors_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BrandFont(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "brand_fonts"
    __table_args__ = (Index("ix_brand_fonts_org_brand", "organization_id", "brand_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    family: Mapped[str] = mapped_column(String(200), nullable=False)
    source_asset_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    usage_role: Mapped[str] = mapped_column(String(64), nullable=False, default="body")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BrandLogo(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "brand_logos"
    __table_args__ = (Index("ix_brand_logos_org_brand", "organization_id", "brand_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant: Mapped[str] = mapped_column(String(64), nullable=False, default="primary")
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class BrandRule(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "brand_rules"
    __table_args__ = (
        Index("ix_brand_rules_org_brand", "organization_id", "brand_id"),
        Index("ix_brand_rules_brand_type", "brand_id", "rule_type"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Project(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("brief_version > 0", name="brief_version"),
        CheckConstraint("status IN ('draft','active','paused','archived')", name="status"),
        Index("ix_projects_org_created", "organization_id", "created_at"),
        Index("ix_projects_org_status", "organization_id", "status"),
        Index("ix_projects_workspace_created", "workspace_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    brief_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    active_branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectBriefVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "project_brief_versions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "brief_version",
            name="uq_project_brief_versions_project_version",
        ),
        CheckConstraint("brief_version > 0", name="version"),
        CheckConstraint("brief_hash ~ '^[0-9a-f]{64}$'", name="hash"),
        Index(
            "ix_project_brief_versions_org_project",
            "organization_id",
            "project_id",
            "brief_version",
        ),
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
    brief_version: Mapped[int] = mapped_column(Integer, nullable=False)
    brief_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class ProjectSummary(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "project_summaries"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_summaries_project"),
        CheckConstraint("active_run_count >= 0", name="active_runs"),
        CheckConstraint("artifact_count >= 0", name="artifacts"),
        Index("ix_project_summaries_org_activity", "organization_id", "last_activity_at"),
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
    latest_artifact_preview_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    active_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    artifact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class ProjectMember(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="project_user"),
        Index("ix_project_members_org_project", "organization_id", "project_id"),
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
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
