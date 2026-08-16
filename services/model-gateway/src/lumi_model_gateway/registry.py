from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from .models import Capability, ProviderModel


class CapabilitySupport(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class ClaimConfidence(StrEnum):
    VERIFIED_DOCS = "verified_docs"
    LIVE_TEST = "live_test"
    INFERRED = "inferred"


class ModelLifecycle(StrEnum):
    STABLE = "stable"
    PREVIEW = "preview"
    DEPRECATED = "deprecated"
    LEGACY = "legacy"
    SHUTDOWN = "shutdown"


class BenchmarkStatus(StrEnum):
    NOT_MEASURED = "not_measured"
    MEASURED = "measured"


@dataclass(frozen=True, slots=True)
class CapabilityClaim:
    model_key: str
    capability: Capability
    support: CapabilitySupport
    limits: Mapping[str, Any] = field(default_factory=dict)
    confidence: ClaimConfidence = ClaimConfidence.VERIFIED_DOCS
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_ref: str = ""

    def __post_init__(self) -> None:
        if not self.model_key or not self.source_ref:
            raise ValueError("capability claim requires model_key and source_ref")
        if self.observed_at.tzinfo is None:
            raise ValueError("capability claim observed_at must be timezone aware")

    @property
    def route_eligible(self) -> bool:
        return self.support is CapabilitySupport.FULL


@dataclass(frozen=True, slots=True)
class PricingSnapshot:
    pricing_snapshot_id: str
    model_key: str
    metric: str
    currency: str
    unit: str
    price: Decimal
    effective_from: datetime
    observed_at: datetime
    source_ref: str
    expires_at: datetime | None = None
    region: str | None = None
    minimum_charge: Decimal | None = None

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError("price cannot be negative")
        if self.minimum_charge is not None and self.minimum_charge < 0:
            raise ValueError("minimum_charge cannot be negative")
        if self.currency != "USD":
            raise ValueError("NODE-23 v1 normalizes pricing currency to USD")
        if not self.metric or not self.unit or not self.source_ref:
            raise ValueError("pricing metric, unit and source are required")
        if self.effective_from.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("pricing timestamps must be timezone aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("pricing expiry must be timezone aware")

    def effective_at(self, at_time: datetime, *, allow_stale: bool = False) -> bool:
        if at_time.tzinfo is None:
            raise ValueError("pricing query time must be timezone aware")
        if at_time < self.effective_from:
            return False
        if not allow_stale and self.expires_at is not None and at_time > self.expires_at:
            return False
        return True


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    benchmark_score_id: str
    model_key: str
    profile: str
    dataset_version: str
    run_id: str
    sample_count: int
    score: Decimal
    observed_at: datetime
    source_ref: str
    confidence_low: Decimal | None = None
    confidence_high: Decimal | None = None
    statistics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sample_count <= 0:
            raise ValueError("benchmark sample_count must be positive")
        if not Decimal("0") <= self.score <= Decimal("100"):
            raise ValueError("benchmark score must be 0..100")
        if self.observed_at.tzinfo is None:
            raise ValueError("benchmark observed_at must be timezone aware")
        if (self.confidence_low is None) != (self.confidence_high is None):
            raise ValueError("benchmark confidence interval must be a complete pair")
        if self.confidence_low is not None:
            assert self.confidence_high is not None
            if self.confidence_low > self.score or self.confidence_high < self.score:
                raise ValueError("benchmark confidence interval must contain score")


@dataclass(frozen=True, slots=True)
class RoutingWeights:
    quality: Decimal = Decimal("0.35")
    constraint: Decimal = Decimal("0.25")
    cost: Decimal = Decimal("0.15")
    latency: Decimal = Decimal("0.15")
    availability: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        values = (
            self.quality,
            self.constraint,
            self.cost,
            self.latency,
            self.availability,
        )
        if any(value < 0 for value in values):
            raise ValueError("routing weights cannot be negative")
        if sum(values, Decimal("0")) != Decimal("1.00"):
            raise ValueError("routing profile weights must sum to 1.00")


@dataclass(frozen=True, slots=True)
class RoutingProfile:
    name: str
    required_capabilities: tuple[Capability, ...]
    candidate_model_keys: tuple[str, ...]
    selection_gate: str
    weights: RoutingWeights = field(default_factory=RoutingWeights)
    stable_fallback_model_keys: tuple[str, ...] = ()
    minimum_quality: Decimal | None = None
    source_ref: str = "docs/models/route-candidates.json"

    def __post_init__(self) -> None:
        if not self.name or not self.candidate_model_keys:
            raise ValueError("routing profile requires name and candidates")
        if self.minimum_quality is not None and not Decimal("0") <= self.minimum_quality <= 100:
            raise ValueError("minimum quality must be 0..100")


@dataclass(frozen=True, slots=True)
class OrganizationModelPolicy:
    organization_id: UUID
    disabled_providers: frozenset[str] = frozenset()
    allowed_regions: frozenset[str] = frozenset()
    preferred_models: tuple[str, ...] = ()
    max_cost_class: str | None = None
    data_handling_restrictions: frozenset[str] = frozenset()
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("organization policy version must be positive")


@dataclass(frozen=True, slots=True)
class ModelRecord:
    model_key: str
    provider: str
    model: str
    lifecycle: ModelLifecycle
    route_eligible: bool
    observed_at: datetime
    source_refs: tuple[str, ...]
    claims: tuple[CapabilityClaim, ...]
    prices: tuple[PricingSnapshot, ...] = ()
    benchmarks: tuple[BenchmarkScore, ...] = ()
    regions: frozenset[str] = frozenset({"global"})
    revision_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_key or not self.provider or not self.model:
            raise ValueError("model identity is required")
        if self.observed_at.tzinfo is None:
            raise ValueError("model observed_at must be timezone aware")
        if not self.source_refs:
            raise ValueError("model requires at least one source_ref")
        if self.lifecycle in {
            ModelLifecycle.DEPRECATED,
            ModelLifecycle.LEGACY,
            ModelLifecycle.SHUTDOWN,
        } and self.route_eligible:
            raise ValueError("inactive lifecycle cannot be route eligible")

    def claim(self, capability: Capability) -> CapabilityClaim | None:
        for claim in self.claims:
            if claim.capability is capability:
                return claim
        return None

    def supports(self, capability: Capability, *, allow_partial: bool = False) -> bool:
        claim = self.claim(capability)
        if claim is None:
            return False
        if claim.support is CapabilitySupport.FULL:
            return True
        return allow_partial and claim.support is CapabilitySupport.PARTIAL

    def benchmark(self, profile: str) -> BenchmarkScore | None:
        matches = [item for item in self.benchmarks if item.profile == profile]
        if not matches:
            return None
        return max(matches, key=lambda item: (item.observed_at, item.dataset_version, item.run_id))

    def pricing(
        self,
        at_time: datetime,
        *,
        allow_stale: bool = False,
        region: str | None = None,
    ) -> tuple[PricingSnapshot, ...]:
        matches = [
            price
            for price in self.prices
            if price.effective_at(at_time, allow_stale=allow_stale)
            and (price.region is None or region is None or price.region == region)
        ]
        return tuple(sorted(matches, key=lambda item: (item.metric, item.effective_from)))

    def to_provider_model(self, *, registry_snapshot_id: str) -> ProviderModel:
        capabilities = frozenset(
            claim.capability
            for claim in self.claims
            if claim.support in {CapabilitySupport.FULL, CapabilitySupport.PARTIAL}
        )
        if not capabilities:
            capabilities = frozenset({Capability.LLM_REASONING})
        return ProviderModel(
            provider=self.provider,
            model=self.model,
            capabilities=capabilities,
            quality_score=50,
            latency_score=50,
            regions=self.regions,
            paid=True,
            enabled=self.route_eligible,
            registry_snapshot_id=registry_snapshot_id,
            model_revision_id=self.revision_id or self.model_key,
            quality_measured=False,
            latency_measured=False,
        )


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    snapshot_id: str
    version: str
    checksum_sha256: str
    observed_at: datetime
    published_at: datetime
    models: Mapping[str, ModelRecord]
    routing_profiles: Mapping[str, RoutingProfile]
    source_ref: str

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.published_at.tzinfo is None:
            raise ValueError("registry timestamps must be timezone aware")
        if len(self.checksum_sha256) != 64:
            raise ValueError("registry checksum must be sha256 hex")
        object.__setattr__(self, "models", MappingProxyType(dict(self.models)))
        object.__setattr__(
            self,
            "routing_profiles",
            MappingProxyType(dict(self.routing_profiles)),
        )

    def list_models(
        self,
        capability: Capability,
        *,
        policy: OrganizationModelPolicy | None = None,
        allow_partial: bool = False,
    ) -> tuple[ModelRecord, ...]:
        records: list[ModelRecord] = []
        for record in self.models.values():
            if not record.route_eligible:
                continue
            if not record.supports(capability, allow_partial=allow_partial):
                continue
            if policy is not None:
                if record.provider in policy.disabled_providers:
                    continue
                if policy.allowed_regions and "global" not in record.regions:
                    if not record.regions.intersection(policy.allowed_regions):
                        continue
            records.append(record)
        preferred = set(policy.preferred_models if policy else ())
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    0 if item.model_key in preferred else 1,
                    item.provider,
                    item.model,
                ),
            )
        )

    def get_model_snapshot(self, model_key: str) -> ModelRecord:
        try:
            return self.models[model_key]
        except KeyError as exc:
            raise KeyError(f"unknown model_key: {model_key}") from exc

    def get_pricing(
        self,
        model_key: str,
        at_time: datetime,
        *,
        allow_stale_history: bool = False,
        region: str | None = None,
    ) -> tuple[PricingSnapshot, ...]:
        return self.get_model_snapshot(model_key).pricing(
            at_time,
            allow_stale=allow_stale_history,
            region=region,
        )


class CapabilityRegistry:
    def __init__(self, snapshot: RegistrySnapshot) -> None:
        self._snapshot = snapshot
        self._generation = 1
        self._policies: dict[UUID, OrganizationModelPolicy] = {}

    @property
    def generation(self) -> int:
        return self._generation

    def capture_snapshot(self) -> RegistrySnapshot:
        return self._snapshot

    def publish(self, snapshot: RegistrySnapshot) -> None:
        if snapshot.snapshot_id == self._snapshot.snapshot_id:
            if snapshot.checksum_sha256 != self._snapshot.checksum_sha256:
                raise ValueError("published registry snapshot identity is immutable")
            return
        self._snapshot = snapshot
        self._generation += 1

    def invalidate(self, expected_snapshot_id: str | None = None) -> int:
        if expected_snapshot_id is not None and expected_snapshot_id != self._snapshot.snapshot_id:
            return self._generation
        self._generation += 1
        return self._generation

    def set_policy(self, policy: OrganizationModelPolicy) -> None:
        current = self._policies.get(policy.organization_id)
        if current is not None and policy.version <= current.version:
            raise ValueError("organization model policy version must increase")
        self._policies[policy.organization_id] = policy
        self._generation += 1

    def policy_for(self, organization_id: UUID) -> OrganizationModelPolicy | None:
        return self._policies.get(organization_id)

    def list_models(
        self,
        capability: Capability,
        *,
        organization_id: UUID,
        allow_partial: bool = False,
    ) -> tuple[ModelRecord, ...]:
        snapshot = self.capture_snapshot()
        return snapshot.list_models(
            capability,
            policy=self.policy_for(organization_id),
            allow_partial=allow_partial,
        )

    def get_model_snapshot(self, model_key: str) -> ModelRecord:
        return self.capture_snapshot().get_model_snapshot(model_key)

    def get_pricing(
        self,
        model_key: str,
        at_time: datetime,
        *,
        allow_stale_history: bool = False,
        region: str | None = None,
    ) -> tuple[PricingSnapshot, ...]:
        return self.capture_snapshot().get_pricing(
            model_key,
            at_time,
            allow_stale_history=allow_stale_history,
            region=region,
        )

    def rank_profile(
        self,
        profile_name: str,
        *,
        organization_id: UUID,
    ) -> tuple[ModelRecord, ...]:
        snapshot = self.capture_snapshot()
        try:
            profile = snapshot.routing_profiles[profile_name]
        except KeyError as exc:
            raise KeyError(f"unknown routing profile: {profile_name}") from exc
        policy = self.policy_for(organization_id)
        by_key = snapshot.models
        eligible: list[ModelRecord] = []
        for model_key in profile.candidate_model_keys:
            record = by_key.get(model_key)
            if record is None or not record.route_eligible:
                continue
            if any(not record.supports(capability) for capability in profile.required_capabilities):
                continue
            if policy is not None and record.provider in policy.disabled_providers:
                continue
            eligible.append(record)
        return tuple(eligible)


def registry_checksum(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    raise TypeError(f"unsupported registry checksum value: {type(value).__name__}")
