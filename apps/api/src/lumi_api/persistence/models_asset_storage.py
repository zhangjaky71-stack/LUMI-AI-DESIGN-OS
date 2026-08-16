# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class AssetUploadSessionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_upload_sessions"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    storage_upload_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("expected_size > 0", name="expected_size_positive"),
        CheckConstraint(
            "expected_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="expected_checksum_sha256_format",
        ),
        CheckConstraint("mode IN ('single_put','multipart')", name="mode"),
        CheckConstraint(
            "status IN ('pending','uploaded','verifying','completed','rejected','expired','aborted')",
            name="status",
        ),
    )


class AssetValidationReportModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "asset_validation_reports"

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    upload_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("asset_upload_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    expected_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sniffed_mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    media_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(32), nullable=False)
    scan_engine: Mapped[str] = mapped_column(String(120), nullable=False)
    scan_signature: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_codes_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    __table_args__ = (
        CheckConstraint("expected_size >= 0 AND actual_size >= 0", name="sizes_nonnegative"),
        CheckConstraint(
            "expected_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "actual_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksums_format",
        ),
        CheckConstraint(
            "media_kind IN ('image','vector','document','video','font')",
            name="media_kind",
        ),
        CheckConstraint(
            "scan_status IN ('clean','infected','unavailable','error')",
            name="scan_status",
        ),
    )
