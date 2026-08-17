# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
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
    name: Mapped[str] = mapped_column(
        String(240), nullable=False, server_default="Untitled Artifact"
    )
    design_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    rights_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    legal_hold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
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
    base_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "artifact_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_artifact_branches_base_version_id_artifact_versions",
        ),
        nullable=True,
    )
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
    created_by_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="system"
    )
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
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
    parent_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_file_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "artifact_files.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_artifact_versions_primary_file_id_artifact_files",
        ),
        nullable=True,
    )
    design_document_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_document_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    constraint_snapshot_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    rights_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    quality_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    provenance_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="PARTIAL"
    )
    provenance_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 5), nullable=False, server_default="0"
    )
    created_by_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="system"
    )
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "artifact_id", "branch_id", "version_number", name="uq_artifact_version_number"
        ),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(
            "status IN ('draft','ready','approved','rejected','archived')", name="status"
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="quality_score_range",
        ),
        CheckConstraint("id <> parent_version_id", name="not_self_parent"),
        CheckConstraint(
            "provenance_status IN ('FULLY_TRACEABLE','PARTIAL')",
            name="provenance_status",
        ),
        CheckConstraint(
            "provenance_score >= 0 AND provenance_score <= 1",
            name="provenance_score_range",
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
            "edge_type IN ('DERIVED_FROM','EDITED_FROM','GENERATED_FROM','COMPOSED_FROM',"
            "'RESIZED_FROM','EXPORTED_FROM','REFERENCE_USED')",
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
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="original")
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        UniqueConstraint(
            "artifact_version_id",
            "bucket",
            "object_key",
            name="uq_artifact_files_version_bucket_key",
        ),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint(
            "role IN ('preview','original','thumbnail','web-optimized','print-pdf','layer-data')",
            name="role",
        ),
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
    agent_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    generation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_template_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recipe_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    compiler_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    code_git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    constraint_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completeness_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="PARTIAL"
    )
    completeness_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 5), nullable=False, server_default="0"
    )
    missing_fields_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )


class ArtifactVersionApprovalModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "artifact_version_approvals"

    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    approved_by_id: Mapped[str] = mapped_column(String(200), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validation_ref: Mapped[str] = mapped_column(Text, nullable=False)


class ArtifactGcMarkModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "artifact_gc_marks"

    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="MARKED")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    __table_args__ = (
        CheckConstraint("state IN ('MARKED','CANCELLED','DELETED')", name="state"),
        Index(
            "uq_artifact_gc_active_mark",
            "organization_id",
            "bucket",
            "object_key",
            unique=True,
            postgresql_where=sql_text("state = 'MARKED'"),
        ),
        Index(
            "ix_artifact_gc_marks_pending",
            "organization_id",
            "state",
            "not_before",
        ),
    )


class ArtifactGcAuditModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "artifact_gc_audits"

    gc_mark_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_gc_marks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ArtifactOutboxEventModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "artifact_outbox_events"

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    aggregate_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        Index(
            "ix_artifact_outbox_events_pending",
            "published_at",
            "occurred_at",
            postgresql_where=sql_text("published_at IS NULL"),
        ),
    )
