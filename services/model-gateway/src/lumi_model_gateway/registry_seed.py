from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import Capability
from .registry import (
    BenchmarkScore,
    CapabilityClaim,
    CapabilityRegistry,
    CapabilitySupport,
    ClaimConfidence,
    ModelLifecycle,
    ModelRecord,
    PricingSnapshot,
    RegistrySnapshot,
    RoutingProfile,
    RoutingWeights,
    registry_checksum,
)

_ROUTE_CAPABILITIES: dict[str, tuple[Capability, ...]] = {
    "reasoning.director": (Capability.LLM_REASONING,),
    "reasoning.default": (Capability.LLM_REASONING,),
    "reasoning.fast": (Capability.LLM_REASONING,),
    "vision.ocr": (Capability.LLM_VISION,),
    "retrieval.rerank": (Capability.LLM_STRUCTURED_OUTPUT,),
    "image.general": (Capability.IMAGE_GENERATE,),
    "image.hero": (Capability.IMAGE_GENERATE,),
    "image.text_heavy": (Capability.IMAGE_GENERATE,),
    "image.local_edit": (Capability.IMAGE_EDIT,),
    "image.fast_variants": (Capability.IMAGE_GENERATE,),
    "video.general": (Capability.VIDEO_TEXT_TO_VIDEO,),
    "video.fast": (Capability.VIDEO_TEXT_TO_VIDEO,),
    "video.edit": (Capability.VIDEO_IMAGE_TO_VIDEO,),
    "embedding.text": (Capability.EMBEDDING_TEXT,),
    "embedding.multimodal": (Capability.EMBEDDING_MULTIMODAL,),
}


def load_seed_registry(root: Path) -> CapabilityRegistry:
    return CapabilityRegistry(load_seed_snapshot(root))


def load_seed_snapshot(root: Path) -> RegistrySnapshot:
    config_path = root / "config/model-registry.seed.json"
    config = _load_json(config_path)
    provider_payloads = [_load_json(root / path) for path in config["provider_files"]]
    route_payload = _load_json(root / config["route_policy"])
    checksum_payload = {
        "config": config,
        "providers": provider_payloads,
        "routes": route_payload,
    }
    checksum = registry_checksum(checksum_payload)
    observed_at = _as_datetime(config["observed_at"])
    version = str(config["registry_version"])
    models: dict[str, ModelRecord] = {}
    for payload in provider_payloads:
        for record in _provider_models(payload, version=version):
            if record.model_key in models:
                raise ValueError(f"duplicate model_key in seed: {record.model_key}")
            models[record.model_key] = record
    profiles = {profile.name: profile for profile in _routing_profiles(route_payload)}
    _validate_route_references(models, profiles)
    snapshot = RegistrySnapshot(
        snapshot_id=f"registry:{version}:{checksum[:16]}",
        version=version,
        checksum_sha256=checksum,
        observed_at=observed_at,
        published_at=observed_at,
        models=models,
        routing_profiles=profiles,
        source_ref="config/model-registry.seed.json",
    )
    validate_seed_snapshot(snapshot)
    return snapshot


def validate_seed_snapshot(snapshot: RegistrySnapshot) -> None:
    providers = {record.provider for record in snapshot.models.values()}
    if len(providers) < 5:
        raise ValueError("NODE-23 seed must preserve at least five providers")
    if len(snapshot.models) < 28:
        raise ValueError("NODE-23 seed lost NODE-07 model records")
    if len(snapshot.routing_profiles) < 15:
        raise ValueError("NODE-23 seed lost NODE-07 routing profiles")
    for record in snapshot.models.values():
        if not record.source_refs:
            raise ValueError(f"model missing source refs: {record.model_key}")
        if record.lifecycle in {
            ModelLifecycle.DEPRECATED,
            ModelLifecycle.LEGACY,
            ModelLifecycle.SHUTDOWN,
        } and record.route_eligible:
            raise ValueError(f"inactive model is route eligible: {record.model_key}")
        for claim in record.claims:
            if claim.support is CapabilitySupport.UNKNOWN and claim.route_eligible:
                raise ValueError("unknown capability claim became route eligible")
        for benchmark in record.benchmarks:
            if not isinstance(benchmark, BenchmarkScore):
                raise TypeError("invalid benchmark score record")
    for profile in snapshot.routing_profiles.values():
        if not profile.candidate_model_keys:
            raise ValueError(f"routing profile has no candidates: {profile.name}")
        if any(
            snapshot.models[key].lifecycle is ModelLifecycle.PREVIEW
            for key in profile.candidate_model_keys
            if key in snapshot.models
        ) and not profile.stable_fallback_model_keys:
            stable = [
                key
                for key in profile.candidate_model_keys
                if key in snapshot.models
                and snapshot.models[key].lifecycle is ModelLifecycle.STABLE
            ]
            if not stable:
                raise ValueError(
                    f"preview-only route lacks stable fallback: {profile.name}"
                )


def _provider_models(payload: dict[str, Any], *, version: str) -> tuple[ModelRecord, ...]:
    provider = str(payload["provider"])
    observed_at = _as_datetime(payload["observed_at"])
    expires_at = (
        _as_datetime(payload["pricing_expires_at"])
        if payload.get("pricing_expires_at")
        else None
    )
    output: list[ModelRecord] = []
    for item in payload.get("models", []):
        model_key = str(item["registry_id"])
        model_id = str(item["model_id"])
        source_refs = tuple(str(value) for value in item.get("sources") or ())
        if not source_refs:
            source_refs = (f"{provider}:unspecified-source",)
        claims = _claims_for_model(
            model_key,
            item,
            observed_at=observed_at,
            source_ref=source_refs[0],
        )
        prices = _prices_for_model(
            model_key,
            item,
            observed_at=observed_at,
            expires_at=expires_at,
            source_ref=source_refs[0],
            version=version,
        )
        lifecycle = ModelLifecycle(str(item.get("lifecycle") or "stable"))
        metadata = {
            "modalities": tuple(item.get("modalities") or ()),
            "roles": tuple(item.get("documented_roles") or ()),
            "documented_capabilities": dict(item.get("documented_capabilities") or {}),
            "benchmark_status": str(item.get("benchmark_status") or "NOT_MEASURED"),
            "notes": str(item.get("notes") or ""),
        }
        revision_hash = registry_checksum(
            {"version": version, "model": item, "observed_at": observed_at}
        )
        output.append(
            ModelRecord(
                model_key=model_key,
                provider=provider,
                model=model_id,
                lifecycle=lifecycle,
                route_eligible=bool(item.get("route_eligible", False)),
                observed_at=observed_at,
                source_refs=source_refs,
                claims=claims,
                prices=prices,
                benchmarks=(),
                regions=frozenset({"global"}),
                revision_id=f"revision:{version}:{revision_hash[:16]}",
                metadata=metadata,
            )
        )
    return tuple(output)


def _claims_for_model(
    model_key: str,
    item: dict[str, Any],
    *,
    observed_at: datetime,
    source_ref: str,
) -> tuple[CapabilityClaim, ...]:
    modalities = set(str(value) for value in item.get("modalities") or ())
    documented = dict(item.get("documented_capabilities") or {})
    inputs = set(str(value) for value in documented.get("input") or ())
    roles = set(str(value) for value in item.get("documented_roles") or ())
    claims: dict[Capability, CapabilityClaim] = {}

    def add(
        capability: Capability,
        *,
        support: CapabilitySupport = CapabilitySupport.FULL,
        confidence: ClaimConfidence = ClaimConfidence.VERIFIED_DOCS,
        limits: dict[str, Any] | None = None,
    ) -> None:
        claims[capability] = CapabilityClaim(
            model_key=model_key,
            capability=capability,
            support=support,
            limits=dict(limits or {}),
            confidence=confidence,
            observed_at=observed_at,
            source_ref=source_ref,
        )

    if "reasoning" in modalities:
        add(Capability.LLM_REASONING)
    if "vision" in modalities or "image" in inputs:
        if "reasoning" in modalities or "vision" in modalities:
            add(Capability.LLM_VISION)
    if documented.get("structured_output") is True:
        add(Capability.LLM_STRUCTURED_OUTPUT)
    if "image_generation" in modalities or documented.get("image_generation") is True:
        add(Capability.IMAGE_GENERATE)
    if "image_edit" in modalities or documented.get("image_edit") is True:
        add(Capability.IMAGE_EDIT)
    if documented.get("mask_edit") is True:
        add(Capability.IMAGE_MASK_EDIT)
    if documented.get("reference_consistency") is True:
        add(Capability.IMAGE_REFERENCE_CONSISTENCY)
    if documented.get("transparent_background") is True:
        add(Capability.IMAGE_TRANSPARENT_BACKGROUND)
    if "video_generation" in modalities:
        if "text" in inputs or not inputs:
            add(Capability.VIDEO_TEXT_TO_VIDEO)
        if "image" in inputs:
            add(Capability.VIDEO_IMAGE_TO_VIDEO)
    if "video_edit" in modalities:
        add(Capability.VIDEO_IMAGE_TO_VIDEO)
    if "embedding" in modalities:
        if inputs and inputs.issubset({"text"}):
            add(Capability.EMBEDDING_TEXT)
        else:
            add(Capability.EMBEDDING_MULTIMODAL)
            if "text" in inputs:
                add(Capability.EMBEDDING_TEXT)
    if any(role.startswith("vision.ocr") for role in roles):
        add(
            Capability.OCR_DOCUMENT,
            support=CapabilitySupport.PARTIAL,
            confidence=ClaimConfidence.INFERRED,
            limits={"route_semantics": "ocr-like multimodal extraction"},
        )
    return tuple(sorted(claims.values(), key=lambda value: value.capability.value))


def _prices_for_model(
    model_key: str,
    item: dict[str, Any],
    *,
    observed_at: datetime,
    expires_at: datetime | None,
    source_ref: str,
    version: str,
) -> tuple[PricingSnapshot, ...]:
    output: list[PricingSnapshot] = []
    for index, price in enumerate(item.get("pricing") or []):
        metric = str(price.get("metric") or f"metric_{index}")
        amount_key = next(
            (key for key in price if key.startswith("usd_") and key != "usd_currency"),
            "usd" if "usd" in price else None,
        )
        if amount_key is None:
            raise ValueError(f"pricing record has no USD amount: {model_key}/{metric}")
        amount = Decimal(str(price[amount_key]))
        unit = metric if amount_key == "usd" else amount_key.removeprefix("usd_")
        minimum = price.get("minimum_charge_usd")
        identity = registry_checksum(
            {
                "version": version,
                "model_key": model_key,
                "metric": metric,
                "unit": unit,
                "amount": amount,
                "index": index,
            }
        )
        output.append(
            PricingSnapshot(
                pricing_snapshot_id=f"price:{version}:{identity[:16]}",
                model_key=model_key,
                metric=metric,
                currency="USD",
                unit=unit,
                price=amount,
                minimum_charge=None if minimum is None else Decimal(str(minimum)),
                effective_from=observed_at,
                observed_at=observed_at,
                expires_at=expires_at,
                source_ref=source_ref,
            )
        )
    return tuple(output)


def _routing_profiles(payload: dict[str, Any]) -> tuple[RoutingProfile, ...]:
    output: list[RoutingProfile] = []
    for route in payload.get("routes") or []:
        name = str(route["route"])
        if route.get("selected_primary") is not None:
            raise ValueError(
                f"NODE-07 candidate route selected a primary before benchmark: {name}"
            )
        output.append(
            RoutingProfile(
                name=name,
                required_capabilities=_ROUTE_CAPABILITIES.get(name, ()),
                candidate_model_keys=tuple(
                    str(value) for value in route.get("candidates") or ()
                ),
                stable_fallback_model_keys=tuple(
                    str(value) for value in route.get("stable_fallback_candidates") or ()
                ),
                selection_gate=str(route.get("selection_gate") or name),
                weights=RoutingWeights(),
            )
        )
    return tuple(output)


def _validate_route_references(
    models: dict[str, ModelRecord],
    profiles: dict[str, RoutingProfile],
) -> None:
    missing = sorted(
        {
            key
            for profile in profiles.values()
            for key in (*profile.candidate_model_keys, *profile.stable_fallback_model_keys)
            if key not in models
        }
    )
    if missing:
        raise ValueError(f"routing profile references unknown models: {missing}")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"registry source must be an object: {path}")
    return payload


def _as_datetime(value: str) -> datetime:
    if "T" in value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
