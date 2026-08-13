from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin, MutableTimestampMixin


class PasswordCredential(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "password_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_password_credentials_user"),
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="password_credentials_argon2id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailVerificationToken(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_email_verification_tokens_hash"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="email_verification_tokens_hash"),
        Index("ix_email_verification_tokens_user_expires", "user_id", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordResetToken(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_password_reset_tokens_hash"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="password_reset_tokens_hash"),
        Index("ix_password_reset_tokens_user_expires", "user_id", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrganizationInvite(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "organization_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_organization_invites_hash"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="organization_invites_hash"),
        CheckConstraint(
            "role IN ('OWNER','ADMIN','EDITOR','VIEWER','BILLING')",
            name="organization_invites_role",
        ),
        Index("ix_organization_invites_org_email", "organization_id", "email"),
        Index("ix_organization_invites_expires", "expires_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiToken(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        UniqueConstraint("prefix", name="uq_api_tokens_prefix"),
        UniqueConstraint("secret_hash", name="uq_api_tokens_hash"),
        CheckConstraint("secret_hash ~ '^[0-9a-f]{64}$'", name="api_tokens_hash"),
        Index("ix_api_tokens_org_created", "organization_id", "created_at"),
        Index("ix_api_tokens_org_active", "organization_id", "revoked_at", "expires_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
