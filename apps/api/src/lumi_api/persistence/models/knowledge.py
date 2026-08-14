from __future__ import annotations

from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, MutableTimestampMixin


class KnowledgeDocumentModel(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_type",
            "source_id",
            "source_version",
            "source_hash",
            name="source",
        ),
        CheckConstraint(
            "source_type IN ('ASSET','URL','TEXT','ARTIFACT','INTERNAL_DOCUMENT')",
            name="source_type",
        ),
        CheckConstraint(
            "trust IN ('INTERNAL_DATA','USER_CONTENT',"
            "'EXTERNAL_UNTRUSTED','MODEL_GENERATED')",
            name="trust",
        ),
        CheckConstraint(
            "status IN ('PENDING','INDEXING','READY','SUPERSEDED',"
            "'FAILED','DELETED')",
            name="status",
        ),
        CheckConstraint("version > 0", name="version"),
        Index(
            "ix_knowledge_documents_org_project_status",
            "organization_id",
            "project_id",
            "status",
        ),
        Index(
            "ix_knowledge_documents_source_lookup",
            "organization_id",
            "source_type",
            "source_id",
            "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    source_uri: Mapped[str | None] = mapped_column(Text)
    trust: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )


class KnowledgeChunkModel(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "ordinal",
            name="document_ordinal",
        ),
        CheckConstraint("ordinal >= 0", name="ordinal"),
        CheckConstraint("token_estimate > 0", name="tokens"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="content_hash",
        ),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL "
            "AND embedding_version IS NULL AND embedding_dimensions IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_version IS NOT NULL AND embedding_dimensions > 0)",
            name="embedding",
        ),
        Index(
            "ix_knowledge_chunks_org_project",
            "organization_id",
            "project_id",
            "document_id",
        ),
        Index(
            "ix_knowledge_chunks_document",
            "document_id",
            "ordinal",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    locator_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_version: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
