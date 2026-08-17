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


class QualityProfileSnapshotModel(Base):
    __tablename__ = "quality_profile_snapshots"
    profile_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(80), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class QualityGraderCalibrationModel(Base):
    __tablename__ = "quality_grader_calibrations"
    calibration_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    grader_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_revision: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    precision: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    recall: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    false_positive_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    false_negative_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    inter_rater_agreement: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    calibration_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calibration_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ArtifactQualityResultModel(Base):
    __tablename__ = "artifact_quality_results"
    quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False)
    artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    artifact_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_status: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    overall_confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    critic_grader_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    critic_calibration_id: Mapped[str | None] = mapped_column(String(200), ForeignKey("quality_grader_calibrations.calibration_id", ondelete="RESTRICT"), nullable=True)
    critic_calibration_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "profile_version"],
            ["quality_profile_snapshots.profile_id", "quality_profile_snapshots.version"],
            ondelete="RESTRICT",
        ),
    )


class QualityDimensionAssessmentModel(Base):
    __tablename__ = "quality_dimension_assessments"
    quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="CASCADE"), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(80), primary_key=True)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    grader_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    assessment_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class QualityViolationModel(Base):
    __tablename__ = "quality_violations"
    quality_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_quality_results.quality_result_id", ondelete="CASCADE"), primary_key=True)
    violation_id: Mapped[str] = mapped_column(String(240), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    violation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
