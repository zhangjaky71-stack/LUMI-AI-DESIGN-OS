from __future__ import annotations

from datetime import UTC, datetime

from .models import (
    Capability,
    CostConfidence,
    LatencyProfile,
    ModelRequest,
    ProviderModel,
    QualityProfile,
    RouteCandidate,
    RouteDecision,
)
from .ports import HealthPort, ProviderAdapter
from .registry import CapabilityRegistry
from .registry_projection import provider_model_from_record


_QUALITY_MIN = {
    QualityProfile.DRAFT: 0,
    QualityProfile.BALANCED: 40,
    QualityProfile.HIGH: 70,
    QualityProfile.MAX: 85,
}

_LATENCY_MIN = {
    LatencyProfile.INTERACTIVE: 65,
    LatencyProfile.STANDARD: 25,
    LatencyProfile.BATCH: 0,
}


class ProviderRegistry:
    """Execution transports, separate from registry control-plane facts."""

    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}
        self._capability_registry: CapabilityRegistry | None = None

    def bind_capability_registry(
        self,
        registry: CapabilityRegistry,
    ) -> None:
        self._capability_registry = registry

    def register(self, adapter: ProviderAdapter) -> None:
        name = adapter.provider_name
        if name in self._adapters:
            raise ValueError(f"provider already registered: {name}")
        self._adapters[name] = adapter

    def adapter(self, provider: str) -> ProviderAdapter:
        try:
            return self._adapters[provider]
        except KeyError as exc:
            raise KeyError(
                f"provider is not registered: {provider}"
            ) from exc

    def has_adapter(self, provider: str) -> bool:
        return provider in self._adapters

    def supports_capability(
        self,
        provider: str,
        capability: Capability,
    ) -> bool:
        adapter = self.adapter(provider)
        return any(
            capability in model.capabilities
            for model in adapter.models()
        )

    def model(self, provider: str, model_name: str) -> ProviderModel:
        if self._capability_registry is not None:
            snapshot = self._capability_registry.capture_snapshot()
            for record in snapshot.models.values():
                if (
                    record.provider == provider
                    and record.model == model_name
                ):
                    return provider_model_from_record(
                        record,
                        registry_snapshot_id=snapshot.snapshot_id,
                    )
        adapter = self.adapter(provider)
        for model in adapter.models():
            if model.model == model_name:
                return model
        raise KeyError(
            f"model is not registered: {provider}/{model_name}"
        )

    def adapters(self) -> tuple[ProviderAdapter, ...]:
        return tuple(
            self._adapters[name]
            for name in sorted(self._adapters)
        )


class ModelRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        health: HealthPort,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.health = health
        self.capability_registry = capability_registry
        if capability_registry is not None:
            self.registry.bind_capability_registry(capability_registry)

    def resolve_model(
        self,
        provider: str,
        model_name: str,
    ) -> ProviderModel:
        return self.registry.model(provider, model_name)

    def route(self, request: ModelRequest) -> RouteDecision:
        accepted: list[RouteCandidate] = []
        rejected: list[str] = []
        preferred_providers = set(
            request.routing_hints.preferred_providers
        )
        preferred_models = set(
            request.routing_hints.preferred_models
        )
        excluded = set(request.routing_hints.excluded_providers)
        registry_snapshot_id: str | None = None

        if self.capability_registry is not None:
            snapshot = self.capability_registry.capture_snapshot()
            registry_snapshot_id = snapshot.snapshot_id
            pricing_at = datetime.now(UTC)
            policy = self.capability_registry.policy_for(
                request.organization_id
            )
            allow_partial = bool(
                request.constraints.get(
                    "allow_partial_capability",
                    False,
                )
            )
            records = snapshot.list_models(
                request.capability,
                policy=policy,
                allow_partial=allow_partial,
            )
            models = tuple(
                provider_model_from_record(
                    record,
                    registry_snapshot_id=snapshot.snapshot_id,
                    pricing_at=pricing_at,
                )
                for record in records
            )
        else:
            models = tuple(
                model
                for adapter in self.registry.adapters()
                for model in adapter.models()
            )

        for model in models:
            reasons: list[str] = []
            identity = f"{model.provider}/{model.model}"
            if not model.enabled:
                rejected.append(f"{identity}:disabled")
                continue
            if model.provider in excluded:
                rejected.append(f"{identity}:provider_excluded")
                continue
            if request.capability not in model.capabilities:
                continue
            reasons.append("capability_match")
            if not self.registry.has_adapter(model.provider):
                rejected.append(f"{identity}:adapter_unavailable")
                continue
            if not self.registry.supports_capability(
                model.provider,
                request.capability,
            ):
                rejected.append(
                    f"{identity}:adapter_capability_unavailable"
                )
                continue
            adapter = self.registry.adapter(model.provider)

            if (
                model.quality_measured
                and model.quality_score
                < _QUALITY_MIN[request.quality_profile]
            ):
                rejected.append(
                    f"{identity}:quality_below_threshold"
                )
                continue
            reasons.append(
                "quality_measured"
                if model.quality_measured
                else "quality_not_measured"
            )

            if (
                model.latency_measured
                and model.latency_score
                < _LATENCY_MIN[request.latency_profile]
            ):
                rejected.append(
                    f"{identity}:latency_below_threshold"
                )
                continue
            reasons.append(
                "latency_measured"
                if model.latency_measured
                else "latency_not_measured"
            )

            required_region = request.routing_hints.required_region
            if (
                required_region
                and required_region not in model.regions
                and "global" not in model.regions
            ):
                rejected.append(f"{identity}:region_mismatch")
                continue
            if required_region:
                reasons.append("region_match")

            health_snapshot = self.health.snapshot(
                model.provider,
                model.model,
            )
            if not health_snapshot.healthy or health_snapshot.score <= 0:
                rejected.append(f"{identity}:health_filtered")
                continue
            reasons.append("health_ok")

            try:
                adapter.validate(request, model)
                estimate = adapter.estimate_cost(request, model)
            except (TypeError, ValueError) as exc:
                rejected.append(
                    f"{identity}:validation:{type(exc).__name__}"
                )
                continue

            if (
                estimate.amount_usd is None
                and not request.routing_hints.allow_unknown_cost
            ):
                rejected.append(f"{identity}:unknown_cost")
                continue
            if (
                request.budget_limit is not None
                and estimate.amount_usd is not None
                and estimate.amount_usd > request.budget_limit
            ):
                rejected.append(f"{identity}:budget_filtered")
                continue
            if (
                request.budget_limit is not None
                and estimate.amount_usd is not None
            ):
                reasons.append("within_request_budget")

            score = health_snapshot.score
            if model.quality_measured:
                score += model.quality_score
            if model.latency_measured:
                score += model.latency_score
            if model.provider in preferred_providers:
                score += 60
                reasons.append("preferred_provider")
            if model.model in preferred_models:
                score += 80
                reasons.append("preferred_model")
            if estimate.confidence is CostConfidence.EXACT:
                score += 5
            elif estimate.confidence is CostConfidence.UNKNOWN:
                score -= 30
            accepted.append(
                RouteCandidate(
                    model,
                    estimate,
                    health_snapshot,
                    score,
                    tuple(reasons),
                )
            )

        accepted.sort(
            key=lambda item: (
                -item.score,
                item.estimate.amount_usd is None,
                item.estimate.amount_usd
                if item.estimate.amount_usd is not None
                else 0,
                item.model.provider,
                item.model.model,
            )
        )
        return RouteDecision(
            request.request_id,
            tuple(accepted),
            tuple(sorted(set(rejected))),
            registry_snapshot_id,
        )
