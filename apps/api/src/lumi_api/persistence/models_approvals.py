# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_OBJECT_DEFAULT


class ApprovalRequestModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "approval_requests"

    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    request_operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    agent_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    approval_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    subject_version_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    subject_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PENDING")
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    required_permission: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ANY_ONE")
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    min_approvals: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    payload_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    changes_requested_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True)
    interrupt_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resume_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        UniqueConstraint("organization_id", "request_operation_id", name="uq_approval_request_operation"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED','EXPIRED','CANCELLED','SUPERSEDED')", name="status"),
        CheckConstraint("approval_type IN ('CREATIVE_DIRECTION','ARTIFACT_VERSION','BRAND_RULE_SET','BUDGET_INCREASE','EXTERNAL_PUBLISH','DESTRUCTIVE_ACTION','CUSTOM_REVIEW')", name="type"),
        CheckConstraint("policy_mode IN ('ANY_ONE','ALL','MIN_N','ROLE_BASED_SEQUENCE')", name="policy_mode"),
        CheckConstraint("policy_version >= 1 AND min_approvals >= 1", name="policy_numbers"),
        CheckConstraint("subject_snapshot_hash IS NULL OR subject_snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash"),
        CheckConstraint("(interrupt_id IS NULL AND resume_version IS NULL) OR (interrupt_id IS NOT NULL AND resume_version IS NOT NULL AND resume_version >= 0)", name="bridge_pair"),
        CheckConstraint("approval_type <> 'ARTIFACT_VERSION' OR (artifact_version_id IS NOT NULL AND subject_id = artifact_version_id AND subject_snapshot_hash IS NOT NULL)", name="artifact_exact_subject"),
    )


class ApprovalDecisionModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "approval_decisions"

    approval_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    approval_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "operation_id", name="uq_approval_decision_operation"),
        UniqueConstraint("approval_id", "actor_id", name="uq_approval_decision_actor"),
        CheckConstraint("decision IN ('APPROVED','REJECTED','CHANGES_REQUESTED')", name="decision"),
        CheckConstraint("approval_version >= 1", name="approval_version"),
    )


class ApprovalAuditModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "approval_audit_events"

    approval_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalEffectModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "approval_effects"

    approval_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    effect_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("approval_id", "effect_type", name="uq_approval_effect_type"),
        UniqueConstraint("organization_id", "operation_id", name="uq_approval_effect_operation"),
        CheckConstraint("effect_type IN ('ARTIFACT_VERSION_APPROVE','AGENT_RUN_RESUME')", name="type"),
        CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="status"),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
    )
