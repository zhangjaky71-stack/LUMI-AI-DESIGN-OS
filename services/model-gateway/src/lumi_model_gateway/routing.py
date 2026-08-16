from __future__ import annotations

from .models import CostConfidence, LatencyProfile, ModelRequest, QualityProfile, RouteCandidate, RouteDecision
from .ports import HealthPort, ProviderAdapter


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
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        name = adapter.provider_name
        if name in self._adapters:
            raise ValueError(f"provider already registered: {name}")
        self._adapters[name] = adapter

    def adapter(self, provider: str) -> ProviderAdapter:
        try:
            return self._adapters[provider]
        except KeyError as exc:
            raise KeyError(f"provider is not registered: {provider}") from exc

    def adapters(self) -> tuple[ProviderAdapter, ...]:
        return tuple(self._adapters[name] for name in sorted(self._adapters))


class ModelRouter:
    def __init__(self, registry: ProviderRegistry, health: HealthPort) -> None:
        self.registry = registry
        self.health = health

    def route(self, request: ModelRequest) -> RouteDecision:
        accepted: list[RouteCandidate] = []
        rejected: list[str] = []
        preferred_providers = set(request.routing_hints.preferred_providers)
        preferred_models = set(request.routing_hints.preferred_models)
        excluded = set(request.routing_hints.excluded_providers)
        for adapter in self.registry.adapters():
            for model in adapter.models():
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
                if model.quality_score < _QUALITY_MIN[request.quality_profile]:
                    rejected.append(f"{identity}:quality_below_threshold")
                    continue
                if model.latency_score < _LATENCY_MIN[request.latency_profile]:
                    rejected.append(f"{identity}:latency_below_threshold")
                    continue
                if request.routing_hints.required_region:
                    required = request.routing_hints.required_region
                    if required not in model.regions and "global" not in model.regions:
                        rejected.append(f"{identity}:region_mismatch")
                        continue
                    reasons.append("region_match")
                snapshot = self.health.snapshot(model.provider, model.model)
                if not snapshot.healthy or snapshot.score <= 0:
                    rejected.append(f"{identity}:health_filtered")
                    continue
                reasons.append("health_ok")
                try:
                    adapter.validate(request, model)
                    estimate = adapter.estimate_cost(request, model)
                except (TypeError, ValueError) as exc:
                    rejected.append(f"{identity}:validation:{type(exc).__name__}")
                    continue
                if estimate.amount_usd is None and not request.routing_hints.allow_unknown_cost:
                    rejected.append(f"{identity}:unknown_cost")
                    continue
                if request.budget_limit is not None and estimate.amount_usd is not None:
                    if estimate.amount_usd > request.budget_limit:
                        rejected.append(f"{identity}:budget_filtered")
                        continue
                    reasons.append("within_request_budget")
                score = model.quality_score + model.latency_score + snapshot.score
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
                accepted.append(RouteCandidate(model, estimate, snapshot, score, tuple(reasons)))
        accepted.sort(
            key=lambda item: (
                -item.score,
                item.estimate.amount_usd is None,
                item.estimate.amount_usd if item.estimate.amount_usd is not None else 0,
                item.model.provider,
                item.model.model,
            )
        )
        return RouteDecision(request.request_id, tuple(accepted), tuple(sorted(set(rejected))))
