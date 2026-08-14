from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from .errors import NoRouteError, ProviderInvocationError
from .models import (
    Capability,
    LatencyProfile,
    ModelRequest,
    ProviderLatencyClass,
    RouteCandidate,
    RoutingDecision,
    latency_allowed,
    quality_threshold,
)
from .ports import ProviderAdapter, ProviderHealthRegistry, ProviderRegistry


@dataclass(frozen=True, slots=True)
class OrganizationModelPolicy:
    organization_id: UUID
    allowed_providers: frozenset[str] = frozenset()
    denied_providers: frozenset[str] = frozenset()
    denied_models: frozenset[str] = frozenset()
    allowed_regions: frozenset[str] = frozenset()
    max_estimated_request_usd: Decimal | None = None


class ModelPolicyResolver(Protocol):
    def resolve(self, organization_id: UUID) -> OrganizationModelPolicy: ...


class DefaultModelPolicyResolver:
    def resolve(self, organization_id: UUID) -> OrganizationModelPolicy:
        return OrganizationModelPolicy(organization_id=organization_id)


class StaticModelPolicyResolver:
    def __init__(self, policies: tuple[OrganizationModelPolicy, ...]) -> None:
        self._policies = {policy.organization_id: policy for policy in policies}

    def resolve(self, organization_id: UUID) -> OrganizationModelPolicy:
        return self._policies.get(
            organization_id,
            OrganizationModelPolicy(organization_id=organization_id),
        )


@dataclass(frozen=True, slots=True)
class _EvaluatedCandidate:
    adapter: ProviderAdapter
    candidate: RouteCandidate


def _required_capabilities(request: ModelRequest) -> tuple[Capability, ...]:
    raw = request.constraints.get("required_capabilities")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("MODEL_REQUIRED_CAPABILITIES_INVALID")
    capabilities: list[Capability] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("MODEL_REQUIRED_CAPABILITY_INVALID")
        try:
            capability = Capability(item)
        except ValueError as exc:
            raise ValueError(f"MODEL_REQUIRED_CAPABILITY_UNKNOWN:{item}") from exc
        if capability not in capabilities:
            capabilities.append(capability)
    return tuple(capabilities)


class ModelRouter:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        health: ProviderHealthRegistry,
        policy_resolver: ModelPolicyResolver | None = None,
    ) -> None:
        self.registry = registry
        self.health = health
        self.router_policy = policy_resolver or DefaultModelPolicyResolver()
        self.policy_resolver = self.router_policy

    async def route(self, request: ModelRequest) -> RoutingDecision:
        policy = self.policy_resolver.resolve(request.organization_id)
        accepted: list[_EvaluatedCandidate] = []
        rejected: dict[str, tuple[str, ...]] = {}
        for adapter in self.registry.adapters():
            reasons = self._static_rejections(request, policy, adapter)
            key = adapter.descriptor.key
            if reasons:
                rejected[key] = tuple(reasons)
                continue
            try:
                adapter.validate(request)
                estimate = await adapter.estimate_cost(request)
            except ProviderInvocationError as exc:
                rejected[key] = (f"PROVIDER_VALIDATE:{exc.category.value}",)
                continue
            budget_reasons = self._budget_rejections(
                request,
                policy,
                estimate.amount_usd,
            )
            if budget_reasons:
                rejected[key] = tuple(budget_reasons)
                continue
            reason_codes = self._reason_codes(request, adapter)
            score = self._score(request, adapter, estimate.amount_usd)
            accepted.append(
                _EvaluatedCandidate(
                    adapter=adapter,
                    candidate=RouteCandidate(
                        provider=adapter.descriptor.provider,
                        model=adapter.descriptor.model,
                        estimate=estimate,
                        score=score,
                        reason_codes=tuple(reason_codes),
                    ),
                )
            )
        if not accepted:
            details = ";".join(
                f"{key}={','.join(reasons)}"
                for key, reasons in sorted(rejected.items())
            )
            raise NoRouteError(f"no eligible model route: {details}"[:2000])
        accepted.sort(
            key=lambda item: (
                -item.candidate.score,
                item.candidate.provider,
                item.candidate.model,
            )
        )
        return RoutingDecision(
            request_id=request.request_id,
            candidates=tuple(item.candidate for item in accepted),
            rejected=rejected,
        )

    def _static_rejections(
        self,
        request: ModelRequest,
        policy: OrganizationModelPolicy,
        adapter: ProviderAdapter,
    ) -> list[str]:
        descriptor = adapter.descriptor
        reasons: list[str] = []
        if request.capability not in descriptor.capabilities:
            reasons.append("CAPABILITY_MISMATCH")
        required = _required_capabilities(request)
        missing = [capability.value for capability in required if capability not in descriptor.capabilities]
        if missing:
            reasons.append("ADDITIONAL_CAPABILITY_MISMATCH:" + ",".join(sorted(missing)))
        if descriptor.quality_score < quality_threshold(request.quality_profile):
            reasons.append("QUALITY_BELOW_THRESHOLD")
        if not latency_allowed(request.latency_profile, descriptor.latency_class):
            reasons.append("LATENCY_PROFILE_MISMATCH")
        if policy.allowed_providers and descriptor.provider not in policy.allowed_providers:
            reasons.append("ORG_PROVIDER_NOT_ALLOWED")
        if descriptor.provider in policy.denied_providers:
            reasons.append("ORG_PROVIDER_DENIED")
        if descriptor.key in policy.denied_models or descriptor.model in policy.denied_models:
            reasons.append("ORG_MODEL_DENIED")
        requested_region = request.constraints.get("region")
        if requested_region and descriptor.regions:
            if requested_region not in descriptor.regions:
                reasons.append("REGION_UNAVAILABLE")
        if policy.allowed_regions and descriptor.regions:
            if not descriptor.regions.intersection(policy.allowed_regions):
                reasons.append("ORG_REGION_POLICY_MISMATCH")
        if not self.health.healthy(descriptor.provider, descriptor.model):
            reasons.append("PROVIDER_UNHEALTHY")
        return reasons

    def _budget_rejections(
        self,
        request: ModelRequest,
        policy: OrganizationModelPolicy,
        amount_usd: Decimal | None,
    ) -> list[str]:
        limits = [
            limit
            for limit in (
                request.budget_limit_usd,
                policy.max_estimated_request_usd,
            )
            if limit is not None
        ]
        if not limits:
            return []
        if amount_usd is None:
            return ["COST_UNKNOWN_WITH_BUDGET"]
        if amount_usd > min(limits):
            return ["BUDGET_EXCEEDED"]
        return []

    def _reason_codes(
        self,
        request: ModelRequest,
        adapter: ProviderAdapter,
    ) -> list[str]:
        descriptor = adapter.descriptor
        reasons = [
            "CAPABILITY_MATCH",
            "QUALITY_THRESHOLD_MET",
            "LATENCY_PROFILE_MET",
            "PROVIDER_HEALTHY",
            "POLICY_ALLOWED",
            "BUDGET_ALLOWED",
        ]
        if _required_capabilities(request):
            reasons.append("ADDITIONAL_CAPABILITIES_MATCH")
        preferred_provider = request.routing_hints.get("preferred_provider")
        preferred_model = request.routing_hints.get("preferred_model")
        if preferred_provider == descriptor.provider:
            reasons.append("PREFERRED_PROVIDER")
        if preferred_model == descriptor.model:
            reasons.append("PREFERRED_MODEL")
        return reasons

    def _score(
        self,
        request: ModelRequest,
        adapter: ProviderAdapter,
        amount_usd: Decimal | None,
    ) -> int:
        descriptor = adapter.descriptor
        score = descriptor.quality_score * 10
        latency_bonus = {
            ProviderLatencyClass.FAST: 120,
            ProviderLatencyClass.STANDARD: 60,
            ProviderLatencyClass.SLOW: 0,
        }[descriptor.latency_class]
        if request.latency_profile == LatencyProfile.BATCH:
            latency_bonus //= 2
        score += latency_bonus
        if amount_usd is not None:
            score -= min(200, int(amount_usd * Decimal("1000")))
        if request.routing_hints.get("preferred_provider") == descriptor.provider:
            score += 500
        if request.routing_hints.get("preferred_model") == descriptor.model:
            score += 500
        return score
