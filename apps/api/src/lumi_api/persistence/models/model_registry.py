from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, IdMixin


class ModelRegistryVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_registry_versions"
    __table_args__ = (
        UniqueConstraint("version", name="model_registry_versions_version_key"),
        UniqueConstraint("content_hash", name="model_registry_versions_content_hash_key"),
        CheckConstraint("version > 0", name="model_registry_versions_version_check"),
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelRegistryModel(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_registry_models"
    __table_args__ = (
        UniqueConstraint(
            "registry_version_id",
            "model_key",
            name="uq_model_registry_models_version_key",
        ),
        Index("ix_model_registry_models_provider", "registry_version_id", "provider"),
    )

    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_key: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    route_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    regions_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    latency_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    benchmark_status: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)


class ModelCapabilityClaim(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_capability_claims"
    __table_args__ = (
        UniqueConstraint(
            "registry_version_id",
            "model_key",
            "capability",
            name="uq_model_capability_claim_version_key",
        ),
        CheckConstraint(
            "support IN ('full','partial','none','unknown')",
            name="model_capability_claim_support",
        ),
        CheckConstraint(
            "confidence IN ('verified_docs','live_test','inferred')",
            name="model_capability_claim_confidence",
        ),
        Index(
            "ix_model_capability_claim_lookup",
            "registry_version_id",
            "capability",
            "support",
        ),
    )

    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_key: Mapped[str] = mapped_column(String(512), nullable=False)
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    support: Mapped[str] = mapped_column(String(16), nullable=False)
    limits_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)


class ModelPricingSnapshot(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_pricing_snapshots"
    __table_args__ = (
        UniqueConstraint("price_snapshot_key", name="model_pricing_snapshots_price_snapshot_key_key"),
        CheckConstraint("price >= 0", name="model_pricing_snapshots_price_check"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="model_pricing_currency"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > effective_from",
            name="model_pricing_window",
        ),
        Index("ix_model_pricing_lookup", "model_key", "effective_from", "valid_until"),
    )

    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    price_snapshot_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_key: Mapped[str] = mapped_column(String(512), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    unit: Mapped[str] = mapped_column(String(128), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    minimum_charge: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)


class ModelBenchmarkScore(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_benchmark_scores"
    __table_args__ = (
        UniqueConstraint(
            "registry_version_id",
            "model_key",
            "profile",
            "dataset_version",
            "run_id",
            name="uq_model_benchmark_version_identity",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="model_benchmark_scores_score_check",
        ),
        CheckConstraint(
            "sample_count > 0",
            name="model_benchmark_scores_sample_count_check",
        ),
        CheckConstraint(
            "confidence IN ('verified_docs','live_test','inferred')",
            name="model_benchmark_confidence",
        ),
        Index("ix_model_benchmark_lookup", "model_key", "profile", "observed_at"),
    )

    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_key: Mapped[str] = mapped_column(String(512), nullable=False)
    profile: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    statistics_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)


class ModelRoutingProfile(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_routing_profiles"
    __table_args__ = (
        UniqueConstraint(
            "registry_version_id",
            "profile",
            name="uq_model_routing_profile_version",
        ),
    )

    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile: Mapped[str] = mapped_column(String(150), nullable=False)
    required_capabilities_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    candidate_models_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    minimum_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)


class OrganizationModelPolicyRecord(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "organization_model_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "policy_version",
            name="uq_organization_model_policy_version",
        ),
        CheckConstraint("policy_version > 0", name="organization_model_policies_policy_version_check"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="organization_model_policy_window",
        ),
        Index(
            "ix_org_model_policy_effective",
            "organization_id",
            "effective_from",
            "effective_to",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    disabled_providers_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    denied_models_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    allowed_regions_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    max_cost_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_models_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    data_handling_restrictions_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
