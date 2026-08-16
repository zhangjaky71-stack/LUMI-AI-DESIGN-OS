# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, MutableMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_OBJECT_DEFAULT


class RuntimeJobModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "runtime_jobs"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    job_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    traceparent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    output_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "job_kind IN ('image.transform','video.render','asset.preview',"
            "'asset.validate','export.package')",
            name="job_kind",
        ),
        CheckConstraint(
            "status IN ('pending','running','retrying','succeeded','failed','cancelled')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="attempts"),
        CheckConstraint(
            "error_category IS NULL OR error_category IN ('transient','permanent','cancelled')",
            name="error_category",
        ),
    )


class DeadLetterRecordModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "dead_letter_records"

    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    message_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_queue: Mapped[str] = mapped_column(String(200), nullable=False)
    consumer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    exchange_name: Mapped[str] = mapped_column(String(160), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(200), nullable=False)
    error_category: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    traceparent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open")

    __table_args__ = (
        CheckConstraint("message_kind IN ('domain_event','job')", name="message_kind"),
        CheckConstraint(
            "error_category IN ('transient','permanent','cancelled')",
            name="error_category",
        ),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        CheckConstraint("status IN ('open','replayed','discarded')", name="status"),
    )
