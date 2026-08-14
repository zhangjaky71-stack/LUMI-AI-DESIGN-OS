from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CHAR, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, MutableTimestampMixin


class MemoryRecordModel(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "memory_records"
    __table_args__ = (
        CheckConstraint("scope_type IN ('SESSION','USER','PROJECT','BRAND','AGENT','ORGANIZATION')", name="scope"),
        CheckConstraint("kind IN ('PREFERENCE','FACT','DECISION','CONSTRAINT_PREFERENCE','WORKFLOW_LEARNING','EPISODIC_SUMMARY')", name="kind"),
        CheckConstraint("status IN ('ACTIVE','PENDING_CONFIRMATION','SUPERSEDED','DELETED','EXPIRED','REJECTED')", name="status"),
        CheckConstraint("created_by_type IN ('USER','AGENT','SYSTEM')", name="actor"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash"),
        CheckConstraint("(embedding IS NULL AND embedding_model IS NULL AND embedding_version IS NULL AND embedding_dimensions IS NULL) OR (embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedding_version IS NOT NULL AND embedding_dimensions > 0)", name="embedding"),
        Index("ix_memory_records_org_scope", "organization_id", "scope_type", "scope_id"),
        Index("ix_memory_records_semantic_key", "organization_id", "scope_type", "scope_id", "kind", "semantic_key"),
        Index("ix_memory_records_active", "organization_id", "status", "expires_at"),
        Index("ix_memory_records_supersedes", "supersedes_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    content_structured: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(512), nullable=False)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("memory_records.id", ondelete="RESTRICT"))
    retention_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_version: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class MemoryCandidateModel(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "memory_candidates"
    __table_args__ = (
        CheckConstraint("scope_type IN ('SESSION','USER','PROJECT','BRAND','AGENT','ORGANIZATION')", name="scope"),
        CheckConstraint("kind IN ('PREFERENCE','FACT','DECISION','CONSTRAINT_PREFERENCE','WORKFLOW_LEARNING','EPISODIC_SUMMARY')", name="kind"),
        CheckConstraint("created_by_type IN ('USER','AGENT','SYSTEM')", name="actor"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        CheckConstraint("outcome IN ('WRITE','DEDUPLICATE_CONFIRM','REQUIRE_CONFIRMATION','BRAND_RULE_PROPOSAL')", name="outcome"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash"),
        Index("ix_memory_candidates_org_outcome", "organization_id", "outcome", "created_at"),
        Index("ix_memory_candidates_scope_key", "organization_id", "scope_type", "scope_id", "semantic_key"),
    )

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    content_structured: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(512), nullable=False)
    explicit_remember: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    temporal_coexistence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
