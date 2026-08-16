# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class ModelRegistryVersionModel(Base):
    __tablename__ = "model_registry_versions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="published")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelProviderModel(Base):
    __tablename__ = "model_providers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelDefinitionModel(Base):
    __tablename__ = "model_definitions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_providers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    provider_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelRevisionModel(Base):
    __tablename__ = "model_revisions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    route_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    regions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelCapabilityModel(Base):
    __tablename__ = "model_capabilities"

    capability_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelCapabilityClaimModel(Base):
    __tablename__ = "model_capability_claims"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    capability_key: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("model_capabilities.capability_key", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    support: Mapped[str] = mapped_column(String(16), nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    confidence: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelPricingSnapshotModel(Base):
    __tablename__ = "model_pricing_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    unit: Mapped[str] = mapped_column(String(128), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    minimum_charge: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelBenchmarkScoreModel(Base):
    __tablename__ = "model_benchmark_scores"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    profile: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence_low: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    confidence_high: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    statistics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelRoutingProfileModel(Base):
    __tablename__ = "model_routing_profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    registry_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registry_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    profile_key: Mapped[str] = mapped_column(String(128), nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    minimum_quality: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    selection_gate: Mapped[str] = mapped_column(String(255), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelRoutingProfileCandidateModel(Base):
    __tablename__ = "model_routing_profile_candidates"

    routing_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_routing_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model_definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_definitions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )


class OrganizationModelPolicyModel(Base):
    __tablename__ = "organization_model_policies"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    disabled_providers: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    allowed_regions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    preferred_models: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    max_cost_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_handling_restrictions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
