# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TenantMixin, UUIDPrimaryKeyMixin
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT
from .models_artifacts import ArtifactVersionModel
from .models_execution import AgentRunModel
from .models_projects_assets import BrandModel


class BrandGuideProposalModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "brand_guide_proposals"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    source_asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending_review"
    )
    rules_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    citations_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review','approved','rejected','published')",
            name="status",
        ),
    )




class BrandRuleVersionCounterModel(Base, TenantMixin):
    __tablename__ = "brand_rule_version_counters"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        primary_key=True,
    )
    next_version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("next_version >= 1", name="positive"),
    )


class BrandRuleSetVersionModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "brand_rule_set_versions"

    brand_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_set_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    asset_set_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    rules_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    voice_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    visual_style_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    source_proposal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brand_guide_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (
        UniqueConstraint("brand_id", "version_number", name="uq_brand_rule_set_version"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(
            "status IN ('draft','published','retired')",
            name="status",
        ),
        CheckConstraint(
            "source IN ('USER_EXPLICIT','APPROVED_GUIDE_EXTRACTION',"
            "'MANUAL_ADMIN','INFERRED_PROPOSAL')",
            name="source",
        ),
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_format"),
        CheckConstraint(
            "status <> 'published' OR source <> 'INFERRED_PROPOSAL'",
            name="inferred_not_published",
        ),
    )


# NODE-43 adds exact immutable rule-set version references without rewriting the
# older mapped classes. SQLAlchemy declarative models support adding mapped
# columns after class declaration; importing this module registers them in Base.metadata.
setattr(
    BrandModel,
    "active_rule_set_version_id",
    mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brand_rule_set_versions.id", ondelete="SET NULL"),
        nullable=True,
    ),
)
setattr(
    ArtifactVersionModel,
    "brand_rule_set_version_id",
    mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brand_rule_set_versions.id", ondelete="RESTRICT"),
        nullable=True,
    ),
)
setattr(
    AgentRunModel,
    "brand_rule_set_version_id",
    mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("brand_rule_set_versions.id", ondelete="RESTRICT"),
        nullable=True,
    ),
)
