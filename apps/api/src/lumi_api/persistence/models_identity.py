# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, MutableMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_OBJECT_DEFAULT


class UserModel(Base, UUIDPrimaryKeyMixin, MutableMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    __table_args__ = (CheckConstraint("status IN ('active','disabled')", name="status"),)


class OrganizationModel(Base, UUIDPrimaryKeyMixin, MutableMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    plan: Mapped[str] = mapped_column(String(64), nullable=False, server_default="free")
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint("status IN ('active','suspended','closed')", name="status"),
    )


class OrganizationMemberModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "organization_members"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_members_org_user"
        ),
        CheckConstraint(
            "role IN ('owner','admin','editor','viewer','billing')", name="role"
        ),
    )


class WorkspaceModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )


class WorkspaceMemberModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_user"
        ),
        CheckConstraint("role IN ('admin','editor','viewer')", name="role"),
    )


class AuthIdentityModel(Base, UUIDPrimaryKeyMixin, MutableMixin):
    __tablename__ = "auth_identities"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_auth_identity_provider_subject"
        ),
    )
