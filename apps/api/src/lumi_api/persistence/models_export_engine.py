# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExportSpecModel(Base):
    __tablename__ = "export_specs"
    export_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ExportJobModel(Base):
    __tablename__ = "export_jobs"
    export_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("export_specs.export_job_id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    runtime_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("runtime_jobs.id", ondelete="SET NULL"), nullable=True)
    package_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    package_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    job_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(240), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ExportItemModel(Base):
    __tablename__ = "export_items"
    export_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("export_specs.export_job_id", ondelete="CASCADE"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False)
    artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    target_format: Mapped[str] = mapped_column(String(32), nullable=False)
    output_name: Mapped[str] = mapped_column(String(240), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ExportOutputModel(Base):
    __tablename__ = "export_outputs"
    export_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("export_specs.export_job_id", ondelete="CASCADE"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False)
    source_artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    filename: Mapped[str] = mapped_column(String(240), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(200), nullable=False)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ExportDownloadGrantModel(Base):
    __tablename__ = "export_download_grants"
    grant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    export_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("export_specs.export_job_id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    package_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
