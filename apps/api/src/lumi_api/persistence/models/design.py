from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin, MutableTimestampMixin


class DesignDocument(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "design_documents"
    __table_args__ = (
        Index("ix_design_documents_org_project", "organization_id", "project_id"),
        Index("ix_design_documents_project_created", "project_id", "created_at"),
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
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    design_ir_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    active_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class DesignDocumentVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "design_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="design_document_version"),
        UniqueConstraint("document_id", "content_hash", name="design_document_content_hash"),
        Index("ix_design_versions_org_document", "organization_id", "document_id"),
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
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    design_ir_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class Artifact(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_org_project", "organization_id", "project_id"),
        Index("ix_artifacts_project_created", "project_id", "created_at"),
        Index("ix_artifacts_project_kind", "project_id", "kind"),
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
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ArtifactBranch(IdMixin, MutableTimestampMixin, Base):
    __tablename__ = "artifact_branches"
    __table_args__ = (
        UniqueConstraint("artifact_id", "name", name="artifact_branch_name"),
        Index("ix_artifact_branches_org_project", "organization_id", "project_id"),
        Index("ix_artifact_branches_artifact", "artifact_id"),
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
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    head_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class ArtifactVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version_number", name="artifact_version_number"),
        UniqueConstraint("artifact_id", "content_hash", name="artifact_content_hash"),
        Index("ix_artifact_versions_org_artifact", "organization_id", "artifact_id"),
        Index("ix_artifact_versions_branch_created", "branch_id", "created_at"),
        Index("ix_artifact_versions_status", "organization_id", "status"),
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
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_branches.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class ArtifactEdge(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "artifact_edges"
    __table_args__ = (
        CheckConstraint(
            "from_artifact_version_id <> to_artifact_version_id",
            name="artifact_edge_no_self_loop",
        ),
        UniqueConstraint(
            "from_artifact_version_id",
            "to_artifact_version_id",
            "edge_type",
            name="artifact_edge_identity",
        ),
        Index("ix_artifact_edges_org_from", "organization_id", "from_artifact_version_id"),
        Index("ix_artifact_edges_org_to", "organization_id", "to_artifact_version_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ArtifactFile(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "artifact_files"
    __table_args__ = (
        UniqueConstraint("artifact_version_id", "format", name="artifact_file_format"),
        Index("ix_artifact_files_org_version", "organization_id", "artifact_version_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)


class ArtifactProvenance(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "artifact_provenance"
    __table_args__ = (
        Index("ix_artifact_provenance_org_version", "organization_id", "artifact_version_id"),
        Index("ix_artifact_provenance_source", "source_type", "source_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
