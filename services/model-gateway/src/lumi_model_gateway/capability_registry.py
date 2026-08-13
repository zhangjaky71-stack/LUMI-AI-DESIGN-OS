from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, NAMESPACE_URL, uuid5

from .models import Capability


class SupportLevel(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class EvidenceConfidence(StrEnum):
    VERIFIED_DOCS = "verified_docs"
    LIVE_TEST = "live_test"
    INFERRED = "inferred"


@dataclass(frozen=True, slots=True)
class RegistryModelSnapshot:
    model_key: str
    provider: str
    model: str
    lifecycle: str
    route_eligible: bool
    observed_at: datetime
    source_ref: str
    regions: tuple[str, ...] = ()
    latency_class: str | None = None
    benchmark_status: str = "NOT_MEASURED"


@dataclass(frozen=True, slots=True)
class CapabilityClaim:
    model_key: str
    capability: Capability
    support: SupportLevel
    limits_json: str
    confidence: EvidenceConfidence
    observed_at: datetime
    source_ref: str

    @property
    def limits(self) -> dict[str, Any]:
        value = json.loads(self.limits_json)
        if not isinstance(value, dict):
            raise ValueError("MODEL_REGISTRY_LIMITS_INVALID")
        return value


@dataclass(frozen=True, slots=True)
class PricingSnapshot:
    price_snapshot_id: str
    model_key: str
    currency: str
    unit: str
    price: Decimal
    minimum_charge: Decimal | None
    effective_from: datetime
    valid_until: datetime | None
    observed_at: datetime
    source_ref: str


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    model_key: str
    profile: str
    score: Decimal
    dataset_version: str
    run_id: str
    sample_count: int
    statistics_json: str
    confidence: EvidenceConfidence
    observed_at: datetime
    source_ref: str


@dataclass(frozen=True, slots=True)
class RoutingProfile:
    profile: str
    required_capabilities: tuple[Capability, ...]
    candidate_models: tuple[str, ...]
    weights_json: str
    minimum_json: str
    observed_at: datetime
    source_ref: str


@dataclass(frozen=True, slots=True)
class RegistryOrganizationPolicy:
    organization_id: UUID
    policy_version: int
    disabled_providers: frozenset[str] = frozenset()
    denied_models: frozenset[str] = frozenset()
    allowed_regions: frozenset[str] = frozenset()
    max_cost_class: str | None = None
    preferred_models: tuple[str, ...] = ()
    data_handling_restrictions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    snapshot_id: UUID
    registry_version: int
    source_registry_version: str
    content_hash: str
    observed_at: datetime
    source_ref: str
    models: tuple[RegistryModelSnapshot, ...]
    capability_claims: tuple[CapabilityClaim, ...]
    pricing: tuple[PricingSnapshot, ...]
    benchmarks: tuple[BenchmarkScore, ...]
    routing_profiles: tuple[RoutingProfile, ...]
    organization_policies: tuple[RegistryOrganizationPolicy, ...] = ()

    def model(self, model_key: str) -> RegistryModelSnapshot | None:
        return next((item for item in self.models if item.model_key == model_key), None)

    def claim(
        self,
        model_key: str,
        capability: Capability,
    ) -> CapabilityClaim | None:
        return next(
            (
                item
                for item in self.capability_claims
                if item.model_key == model_key and item.capability == capability
            ),
            None,
        )

    def support(self, model_key: str, capability: Capability) -> SupportLevel:
        claim = self.claim(model_key, capability)
        return claim.support if claim is not None else SupportLevel.UNKNOWN

    def price_snapshot(self, price_snapshot_id: str) -> PricingSnapshot | None:
        return next(
            (
                item
                for item in self.pricing
                if item.price_snapshot_id == price_snapshot_id
            ),
            None,
        )

    def pricing_at(
        self,
        model_key: str,
        at_time: datetime,
        *,
        unit: str | None = None,
    ) -> tuple[PricingSnapshot, ...]:
        at_time = _utc(at_time)
        rows = [
            item
            for item in self.pricing
            if item.model_key == model_key
            and (unit is None or item.unit == unit)
            and item.effective_from <= at_time
            and (item.valid_until is None or at_time < item.valid_until)
        ]
        rows.sort(
            key=lambda item: (item.effective_from, item.price_snapshot_id),
            reverse=True,
        )
        return tuple(rows)

    def benchmark(self, model_key: str, profile: str) -> BenchmarkScore | None:
        rows = [
            item
            for item in self.benchmarks
            if item.model_key == model_key and item.profile == profile
        ]
        if not rows:
            return None
        rows.sort(key=lambda item: (item.observed_at, item.run_id), reverse=True)
        return rows[0]

    def organization_policy(
        self,
        organization_id: UUID,
    ) -> RegistryOrganizationPolicy | None:
        rows = [
            item
            for item in self.organization_policies
            if item.organization_id == organization_id
        ]
        if not rows:
            return None
        return max(rows, key=lambda item: item.policy_version)

    def list_models(
        self,
        capability: Capability,
        *,
        organization_id: UUID | None = None,
        allow_partial: bool = False,
    ) -> tuple[RegistryModelSnapshot, ...]:
        policy = self.organization_policy(organization_id) if organization_id else None
        allowed_support = {SupportLevel.FULL}
        if allow_partial:
            allowed_support.add(SupportLevel.PARTIAL)
        rows: list[RegistryModelSnapshot] = []
        for model in self.models:
            if not model.route_eligible:
                continue
            if self.support(model.model_key, capability) not in allowed_support:
                continue
            if policy and model.provider in policy.disabled_providers:
                continue
            if policy and model.model_key in policy.denied_models:
                continue
            if policy and policy.allowed_regions and model.regions:
                if not set(model.regions).intersection(policy.allowed_regions):
                    continue
            rows.append(model)
        return tuple(sorted(rows, key=lambda item: item.model_key))

    def quality_score(self, model_key: str, capability: Capability) -> int | None:
        profile = _benchmark_profile_for(capability)
        if profile is None:
            return None
        score = self.benchmark(model_key, profile)
        if score is None:
            return None
        return max(0, min(100, int(score.score)))

    def rank_candidates(
        self,
        profile_name: str,
        *,
        organization_id: UUID | None = None,
    ) -> tuple[str, ...]:
        profile = next(
            (
                item
                for item in self.routing_profiles
                if item.profile == profile_name
            ),
            None,
        )
        if profile is None:
            raise KeyError(f"MODEL_ROUTING_PROFILE_NOT_FOUND:{profile_name}")
        policy = self.organization_policy(organization_id) if organization_id else None
        ranked: list[tuple[Decimal, int, str]] = []
        for index, model_key in enumerate(profile.candidate_models):
            model = self.model(model_key)
            if model is None or not model.route_eligible:
                continue
            if policy and model.provider in policy.disabled_providers:
                continue
            if policy and model_key in policy.denied_models:
                continue
            if any(
                self.support(model_key, capability) != SupportLevel.FULL
                for capability in profile.required_capabilities
            ):
                continue
            scores = [
                self.benchmark(model_key, name)
                for name in _quality_profiles_for_route(profile_name)
            ]
            measured = [item.score for item in scores if item is not None]
            quality = (
                sum(measured, Decimal("0")) / len(measured)
                if measured
                else Decimal("0")
            )
            preferred = (
                Decimal("1000")
                if policy and model_key in policy.preferred_models
                else Decimal("0")
            )
            ranked.append((preferred + quality, -index, model_key))
        ranked.sort(reverse=True)
        return tuple(item[2] for item in ranked)


class CapabilityRegistry(Protocol):
    def snapshot(self) -> RegistrySnapshot: ...


class InMemoryCapabilityRegistry:
    def __init__(self, snapshot: RegistrySnapshot) -> None:
        self._snapshot = snapshot
        self._lock = threading.Lock()

    def snapshot(self) -> RegistrySnapshot:
        with self._lock:
            return self._snapshot

    def activate(self, snapshot: RegistrySnapshot) -> None:
        with self._lock:
            current = self._snapshot
            if snapshot.registry_version < current.registry_version:
                raise ValueError("MODEL_REGISTRY_VERSION_REGRESSION")
            if (
                snapshot.registry_version == current.registry_version
                and snapshot.content_hash != current.content_hash
            ):
                raise ValueError("MODEL_REGISTRY_VERSION_CONTENT_CONFLICT")
            self._snapshot = snapshot

    def invalidate(self, expected_content_hash: str) -> bool:
        with self._lock:
            return self._snapshot.content_hash != expected_content_hash


def compile_registry_seed(
    seed_path: Path,
    *,
    repository_root: Path,
) -> RegistrySnapshot:
    seed = _read_json_yaml(seed_path)
    manifest_path = repository_root / str(seed["source_manifest"])
    manifest = _read_json(manifest_path)
    source_registry_version = str(seed["source_registry_version"])
    if manifest.get("registry_version") != source_registry_version:
        raise ValueError("MODEL_REGISTRY_SOURCE_VERSION_MISMATCH")
    provider_files = tuple(str(item) for item in seed["provider_files"])
    models: list[RegistryModelSnapshot] = []
    claims: list[CapabilityClaim] = []
    pricing: list[PricingSnapshot] = []
    observed_values: list[datetime] = []
    source_bytes: list[bytes] = [seed_path.read_bytes(), manifest_path.read_bytes()]
    providers_seen: set[str] = set()
    for relative in provider_files:
        path = repository_root / relative
        source_bytes.append(path.read_bytes())
        provider_payload = _read_json(path)
        provider = str(provider_payload["provider"])
        if provider in providers_seen:
            raise ValueError(f"MODEL_REGISTRY_PROVIDER_DUPLICATE:{provider}")
        providers_seen.add(provider)
        observed_at = _date_time(str(provider_payload["observed_at"]))
        observed_values.append(observed_at)
        valid_until = _date_time(str(provider_payload["pricing_expires_at"]))
        for raw in provider_payload["models"]:
            model_key = str(raw["registry_id"])
            model_id = str(raw["model_id"])
            source_ref = f"{relative}#{model_key}"
            models.append(
                RegistryModelSnapshot(
                    model_key=model_key,
                    provider=provider,
                    model=model_id,
                    lifecycle=str(raw["lifecycle"]),
                    route_eligible=bool(raw["route_eligible"]),
                    observed_at=observed_at,
                    source_ref=source_ref,
                    benchmark_status=str(
                        raw.get("benchmark_status", "NOT_MEASURED")
                    ),
                )
            )
            for capability, limits in _capability_map(raw):
                claims.append(
                    CapabilityClaim(
                        model_key=model_key,
                        capability=capability,
                        support=SupportLevel.FULL,
                        limits_json=_canonical_json(limits),
                        confidence=EvidenceConfidence.VERIFIED_DOCS,
                        observed_at=observed_at,
                        source_ref=source_ref,
                    )
                )
            for raw_price in raw.get("pricing", []):
                unit, price = _price(raw_price)
                key_payload = (
                    f"{source_registry_version}|{model_key}|{unit}|{price}"
                )
                price_id = hashlib.sha256(key_payload.encode()).hexdigest()[:32]
                pricing.append(
                    PricingSnapshot(
                        price_snapshot_id=price_id,
                        model_key=model_key,
                        currency="USD",
                        unit=unit,
                        price=price,
                        minimum_charge=(
                            price if "minimum" in str(raw_price["metric"]) else None
                        ),
                        effective_from=observed_at,
                        valid_until=valid_until,
                        observed_at=observed_at,
                        source_ref=source_ref,
                    )
                )
    required_providers = set(str(item) for item in manifest["required_providers"])
    if providers_seen != required_providers:
        raise ValueError("MODEL_REGISTRY_PROVIDER_SET_MISMATCH")
    route_path = repository_root / str(seed["route_policy"])
    benchmark_path = repository_root / str(seed["benchmark_suite"])
    source_bytes.extend((route_path.read_bytes(), benchmark_path.read_bytes()))
    routes = _read_json(route_path)
    routing_profiles = tuple(
        _compile_route(
            item,
            str(routes["observed_at"]),
            str(seed["route_policy"]),
        )
        for item in routes["routes"]
    )
    canonical = _snapshot_payload(models, claims, pricing, routing_profiles, seed)
    content_hash = hashlib.sha256(
        b"\n".join(source_bytes) + _canonical_json(canonical).encode("utf-8")
    ).hexdigest()
    snapshot_id = uuid5(NAMESPACE_URL, f"lumi:model-registry:{content_hash}")
    return RegistrySnapshot(
        snapshot_id=snapshot_id,
        registry_version=int(seed["registry_version"]),
        source_registry_version=source_registry_version,
        content_hash=content_hash,
        observed_at=max(observed_values),
        source_ref=str(seed["source_ref"]),
        models=tuple(sorted(models, key=lambda item: item.model_key)),
        capability_claims=tuple(
            sorted(
                claims,
                key=lambda item: (item.model_key, item.capability.value),
            )
        ),
        pricing=tuple(sorted(pricing, key=lambda item: (item.model_key, item.unit))),
        benchmarks=(),
        routing_profiles=tuple(
            sorted(routing_profiles, key=lambda item: item.profile)
        ),
    )


def _capability_map(
    raw: dict[str, Any],
) -> tuple[tuple[Capability, dict[str, Any]], ...]:
    documented = raw.get("documented_capabilities", {})
    limits = dict(documented) if isinstance(documented, dict) else {}
    inputs = {str(item) for item in limits.get("input", [])}
    mapped: set[Capability] = set()
    modalities = {str(item) for item in raw.get("modalities", [])}
    for modality in modalities:
        capability = {
            "reasoning": Capability.LLM_REASONING,
            "vision": Capability.LLM_VISION,
            "image_generation": Capability.IMAGE_GENERATE,
            "image_edit": Capability.IMAGE_EDIT,
            "video_generation": Capability.VIDEO_TEXT_TO_VIDEO,
            "embedding": Capability.EMBEDDING_TEXT,
        }.get(modality)
        if capability is not None:
            mapped.add(capability)
    if bool(limits.get("structured_output")):
        mapped.add(Capability.LLM_STRUCTURED_OUTPUT)
    if "video_generation" in modalities and "image" in inputs:
        mapped.add(Capability.VIDEO_IMAGE_TO_VIDEO)
    if "embedding" in modalities and inputs.intersection(
        {"image", "video", "audio", "pdf"}
    ):
        mapped.add(Capability.EMBEDDING_MULTIMODAL)
    return tuple(
        (capability, limits)
        for capability in sorted(mapped, key=lambda item: item.value)
    )


def _price(raw: dict[str, Any]) -> tuple[str, Decimal]:
    metric = str(raw["metric"])
    if "usd_per_million" in raw:
        return f"{metric}:per_million", Decimal(str(raw["usd_per_million"]))
    if "usd_per_second" in raw:
        return f"{metric}:per_second", Decimal(str(raw["usd_per_second"]))
    if "usd_per_image" in raw:
        return f"{metric}:per_image", Decimal(str(raw["usd_per_image"]))
    if "usd" in raw:
        return f"{metric}:native", Decimal(str(raw["usd"]))
    raise ValueError(f"MODEL_REGISTRY_PRICE_UNIT_UNKNOWN:{metric}")


def _compile_route(
    raw: dict[str, Any],
    observed_at: str,
    source_ref: str,
) -> RoutingProfile:
    name = str(raw["route"])
    weights = {
        "quality": "0.45",
        "constraint": "0.30",
        "cost": "0.10",
        "latency": "0.10",
        "availability": "0.05",
    }
    return RoutingProfile(
        profile=name,
        required_capabilities=_route_capabilities(name),
        candidate_models=tuple(str(item) for item in raw["candidates"]),
        weights_json=_canonical_json(weights),
        minimum_json=_canonical_json({}),
        observed_at=_date_time(observed_at),
        source_ref=source_ref,
    )


def _route_capabilities(name: str) -> tuple[Capability, ...]:
    if name.startswith("image."):
        if name == "image.local_edit":
            return (Capability.IMAGE_EDIT,)
        return (Capability.IMAGE_GENERATE,)
    if name == "video.edit":
        return ()
    if name.startswith("video."):
        return (Capability.VIDEO_TEXT_TO_VIDEO,)
    if name == "embedding.multimodal":
        return (Capability.EMEDDING_MULTIMODAL,)  # type: ignore[attr-defined]
    if name.startswith("embedding."):
        return (Capability.EMBEDDING_TEXT,)
    if name == "vision.ocr":
        return (Capability.LLM_VISION,)
    return (Capability.LLM_REASONING,)


def _benchmark_profile_for(capability: Capability) -> str | None:
    return {
        Capability.LLM_REASONING: "planning",
        Capability.LLM_STRUCTURED_OUTPUT: "structured_ir",
        Capability.IMAGE_GENERATE: "product_identity",
        Capability.IMAGE_EDIT: "image_edit_precision",
        Capability.VIDEO_TEXT_TO_VIDEO: "video_motion",
    }.get(capability)


def _quality_profiles_for_route(name: str) -> tuple[str, ...]:
    if name == "image.local_edit":
        return ("image_edit_precision", "product_identity")
    if name.startswith("image."):
        return ("product_identity", "image_text_fidelity")
    if name.startswith("video."):
        return ("video_motion",)
    return ("planning", "structured_ir")


def _snapshot_payload(
    models: list[RegistryModelSnapshot],
    claims: list[CapabilityClaim],
    pricing: list[PricingSnapshot],
    profiles: tuple[RoutingProfile, ...],
    seed: dict[str, Any],
) -> dict[str, Any]:
    return {
        "registry_version": seed["registry_version"],
        "models": [item.model_key for item in models],
        "claims": [
            (item.model_key, item.capability.value, item.support.value)
            for item in claims
        ],
        "pricing": [
            (
                item.price_snapshot_id,
                item.model_key,
                item.unit,
                str(item.price),
            )
            for item in pricing
        ],
        "profiles": [
            (item.profile, list(item.candidate_models)) for item in profiles
        ],
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"MODEL_REGISTRY_DOCUMENT_INVALID:{path}")
    return value


def _read_json_yaml(path: Path) -> dict[str, Any]:
    return _read_json(path)


def _date_time(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("MODEL_REGISTRY_NAIVE_DATETIME")
    return value.astimezone(UTC)
