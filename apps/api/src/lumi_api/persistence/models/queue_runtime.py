from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, MutableTimestampMixin


class DeadLetterRecord(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "dead_letter_records"
    __table_args__ = (
        CheckConstraint(
            "message_kind IN ('job', 'domain_event')",
            name="message_kind",
        ),
        CheckConstraint(
            "error_category IN ('transient', 'permanent', 'cancelled')",
            name="error_category",
        ),
        Index("ix_dead_letter_records_queue_failure", "source_queue", "last_failed_at"),
        Index("ix_dead_letter_records_org_failure", "organization_id", "last_failed_at"),
        Index("ix_dead_letter_records_message", "message_id"),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    message_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_queue: Mapped[str] = mapped_column(String(150), nullable=False)
    consumer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    exchange_name: Mapped[str] = mapped_column(String(150), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(255), nullable=False)
    error_category: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
