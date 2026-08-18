# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class GovernanceRetentionPolicyModel(Base):
    __tablename__ = "governance_retention_policies"
    __table_args__ = (
        UniqueConstraint("retention_class", "policy_version", name="uq_governance_retention_policy"),
        CheckConstraint(
            "retention_class IN ('SECURITY_AUDIT','BILLING','CONTENT','AGENT_TRACE','TEMP_SANDBOX','EXPORT','ANALYTICS')",
            name="ck_governance_retention_class",
        ),
        CheckConstraint("retain_days >= 1", name="ck_governance_retention_days"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    retention_class: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    retain_days: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index(
    "uq_governance_retention_active_class",
    GovernanceRetentionPolicyModel.retention_class,
    unique=True,
    postgresql_where=GovernanceRetentionPolicyModel.active.is_(True),
)


class GovernanceLegalHoldModel(Base):
    __tablename__ = "governance_legal_holds"
    __table_args__ = (
        UniqueConstraint("organization_id", "hold_key", name="uq_governance_legal_hold_key"),
        CheckConstraint(
            "scope_type IN ('ORGANIZATION','USER','PROJECT','ASSET','ARTIFACT','AUDIT')",
            name="ck_governance_legal_hold_scope",
        ),
        CheckConstraint("length(btrim(reason)) >= 8", name="ck_governance_legal_hold_reason"),
        CheckConstraint(
            "(released_at IS NULL AND released_by_user_id IS NULL AND release_reason IS NULL) OR "
            "(released_at IS NOT NULL AND released_by_user_id IS NOT NULL AND release_reason IS NOT NULL AND length(btrim(release_reason)) >= 8)",
            name="ck_governance_legal_hold_release",
        ),
        Index("ix_governance_legal_hold_scope", "organization_id", "scope_type", "scope_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    hold_key: Mapped[str] = mapped_column(String(160), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(Text)


class GovernanceDeletionRequestModel(Base):
    __tablename__ = "governance_deletion_requests"
    __table_args__ = (
        CheckConstraint("subject_type IN ('USER','ORGANIZATION')", name="ck_governance_deletion_subject"),
        CheckConstraint(
            "status IN ('IDENTIFIED','HOLD_BLOCKED','DEACTIVATED','ERASING','COMPLETED','FAILED')",
            name="ck_governance_deletion_status",
        ),
        CheckConstraint(
            "object_gc_status IN ('PENDING','BLOCKED','RUNNING','COMPLETED','FAILED') AND "
            "search_gc_status IN ('PENDING','BLOCKED','RUNNING','COMPLETED','FAILED')",
            name="ck_governance_gc_status",
        ),
        CheckConstraint("length(btrim(reason)) >= 8", name="ck_governance_deletion_reason"),
        Index("ix_governance_deletion_org_status", "organization_id", "status", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="IDENTIFIED")
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    hold_blockers_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT)
    object_gc_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    search_gc_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class GovernanceAuditExportModel(Base):
    __tablename__ = "governance_audit_exports"
    __table_args__ = (
        CheckConstraint("export_format IN ('JSON','CSV')", name="ck_governance_audit_export_format"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED')",
            name="ck_governance_audit_export_status",
        ),
        Index("ix_governance_audit_export_org_requested", "organization_id", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    export_format: Mapped[str] = mapped_column(String(8), nullable=False)
    filters_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    result_ref: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
