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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .model_support import JSON_OBJECT_DEFAULT


class PlatformAdminPrincipalModel(Base):
    __tablename__ = "platform_admin_principals"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_platform_admin_principal_user"),
        CheckConstraint(
            "role IN ('SUPPORT_READ','OPS','BILLING_ADMIN','AI_CONFIG_ADMIN','SECURITY_ADMIN','SUPER_ADMIN')",
            name="ck_platform_admin_role",
        ),
        Index("ix_platform_admin_principal_role_active", "role", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    granted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class PlatformAdminAuditEventModel(Base):
    __tablename__ = "platform_admin_audit_events"
    __table_args__ = (
        Index("ix_platform_admin_audit_created", "created_at"),
        Index("ix_platform_admin_audit_actor_created", "actor_user_id", "created_at"),
        Index(
            "ix_platform_admin_audit_resource",
            "resource_type",
            "resource_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    target_organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlatformFeatureFlagModel(Base):
    __tablename__ = "platform_feature_flags"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('global','organization','user')",
            name="ck_platform_feature_flag_scope",
        ),
        CheckConstraint(
            "((scope='global' AND target_id IS NULL) OR "
            "(scope<>'global' AND target_id IS NOT NULL))",
            name="ck_platform_feature_flag_target",
        ),
        Index("ix_platform_feature_flags_lookup", "flag_key", "scope", "target_id"),
        Index("ix_platform_feature_flags_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    flag_key: Mapped[str] = mapped_column(String(160), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(255))
    value_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    owner: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    security_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


Index(
    "uq_platform_feature_flag_scope",
    PlatformFeatureFlagModel.flag_key,
    PlatformFeatureFlagModel.scope,
    func.coalesce(PlatformFeatureFlagModel.target_id, ""),
    unique=True,
)


class PlatformBreakGlassGrantModel(Base):
    __tablename__ = "platform_break_glass_grants"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_platform_break_glass_expiry"),
        Index("ix_platform_break_glass_actor_expiry", "actor_user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
