# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RepairPolicySnapshotModel(Base):
    __tablename__ = "repair_policy_snapshots"
    policy_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AutoRepairJobModel(Base):
    __tablename__ = "auto_repair_jobs"
    repair_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    source_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False)
    source_artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    source_quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="RESTRICT"), nullable=False)
    original_branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_branches.id", ondelete="RESTRICT"), nullable=False)
    original_head_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    working_artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    current_quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="RESTRICT"), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(200), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    final_artifact_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="SET NULL"), nullable=True)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    job_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["repair_policy_snapshots.policy_id", "repair_policy_snapshots.version"],
            ondelete="RESTRICT",
        ),
    )


class AutoRepairAttemptModel(Base):
    __tablename__ = "auto_repair_attempts"
    repair_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auto_repair_jobs.repair_job_id", ondelete="CASCADE"), primary_key=True)
    iteration: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    before_quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="RESTRICT"), nullable=False)
    repair_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(48), nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    actual_cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    reservation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    candidate_artifact_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=True)
    after_quality_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="RESTRICT"), nullable=True)
    before_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    after_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    score_delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    attempt_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RepairLearningSignalModel(Base):
    __tablename__ = "repair_learning_signals"
    learning_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    repair_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    candidate_artifact_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="SET NULL"), nullable=True)
    source_quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="RESTRICT"), nullable=False)
    candidate_quality_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="SET NULL"), nullable=True)
    repair_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    violation_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    action_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    before_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    after_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    human_decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    human_decision_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    human_decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eligible_for_training: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    governance_approval_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["repair_job_id", "iteration"],
            ["auto_repair_attempts.repair_job_id", "auto_repair_attempts.iteration"],
            ondelete="CASCADE",
        ),
    )
