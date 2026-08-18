# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_ARRAY_DEFAULT


class CommentThreadModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "comment_threads"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False
    )
    design_node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    x: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    y: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="OPEN")
    needs_reanchor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED')", name="status"),
        CheckConstraint(
            "(status = 'RESOLVED' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL) OR "
            "(status = 'OPEN' AND resolved_by IS NULL AND resolved_at IS NULL)",
            name="resolution_consistency",
        ),
        CheckConstraint("(x IS NULL) = (y IS NULL)", name="anchor_coordinates_pair"),
    )


class CommentModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "comments"

    thread_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comment_threads.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("length(body) <= 20000", name="body_length"),
    )


class CommentRevisionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "comment_revisions"

    comment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    body_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    mentions_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    __table_args__ = (
        UniqueConstraint("comment_id", "revision_number", name="uq_comment_revision_number"),
        CheckConstraint("revision_number >= 1", name="revision_positive"),
        CheckConstraint("action IN ('CREATED','EDITED','DELETED')", name="action"),
        CheckConstraint("length(body_snapshot) <= 20000", name="body_length"),
    )
