# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base,
    CreatedAtMixin,
    MutableMixin,
    SoftDeleteMixin,
    TenantMixin,
    UUIDPrimaryKeyMixin,
)
from .model_support import JSON_OBJECT_DEFAULT


class DesignDocumentModel(
    Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin, SoftDeleteMixin
):
    __tablename__ = "design_documents"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    ir_version: Mapped[str] = mapped_column(String(32), nullable=False)
    head_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "design_document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_design_documents_head_version_id_versions",
        ),
        nullable=True,
    )


class DesignDocumentVersionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "design_document_versions"

    design_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_document_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    __table_args__ = (
        UniqueConstraint(
            "design_document_id",
            "version_number",
            name="uq_design_document_version_number",
        ),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("id <> parent_version_id", name="not_self_parent"),
    )


class ArtifactModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin, SoftDeleteMixin):
    __tablename__ = "artifacts"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    design_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_documents.id", ondelete="SET NULL"),
        nullable=True,
    )


class ArtifactBranchModel(Base, UUIDPrimaryKeyMixin, TenantMixin, MutableMixin):
    __tablename__ = "artifact_branches"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    head_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "artifact_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_artifact_branches_head_version_id_versions",
        ),
        nullable=True,
    )
    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_id", "name", name="uq_artifact_branch_name"
        ),
    )


class ArtifactVersionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "artifact_versions"

    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    created_by_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="system"
    )
    created_by_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "artifact_id", "branch_id", "version_number", name="uq_artifact_version_number"
        ),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("status IN ('draft','ready','approved','rejected')", name="status"),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="quality_score_range",
        ),
    )


class ArtifactEdgeModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "artifact_edges"

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
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        UniqueConstraint(
            "from_artifact_version_id",
            "to_artifact_version_id",
            "edge_type",
            name="uq_artifact_edge",
        ),
        CheckConstraint(
            "from_artifact_version_id <> to_artifact_version_id", name="not_self_edge"
        ),
        CheckConstraint(
            "edge_type IN ('DERIVED_FROM','EDITED_FROM','COMPOSED_FROM','RESIZED_FROM',"
            "'EXPORTED_FROM','GENERATED_FROM_ASSET')",
            name="edge_type",
        ),
    )


class ArtifactFileModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "artifact_files"

    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_artifact_files_bucket_key"),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
    )


class ArtifactProvenanceModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "artifact_provenance"

    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
