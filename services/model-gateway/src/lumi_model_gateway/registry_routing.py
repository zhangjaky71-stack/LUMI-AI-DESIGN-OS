from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

from .capability_registry import CapabilityRegistry, RegistrySnapshot, SupportLevel
from .errors import NoRouteError, ProviderInvocationError
from .models import (
    CostEstimate,
    ModelRequest,
    ModelResult,
    ProviderModel,
    RoutingDecision,
    StreamChunk,
)
from .ports import ProviderAdapter, ProviderHealthRegistry, ProviderRegistry
from .routing import (
    ModelPolicyResolver,
    ModelRouter,
    OrganizationModelPolicy,
    StaticModelPolicyResolver,
)


@dataclass(frozen=True, slots=True)
class _RegistryAdapter:
    delegate: ProviderAdapter
    descriptor: ProviderModel

    def validate(self, request: ModelRequest) -> None:
        self.delegate.validate(request)

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate:
        return await self.delegate.estimate_cost(request)

    async def invoke(self, request: ModelRequest) -> ModelResult:
        return await self.delegate.invoke(request)

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        return self.delegate.stream(request)

    async def get_async_status(self, provider_request_id: str) -> ModelResult:
        return await self.delegate.get_async_status(provider_request_id)

    async def cancel(self, provider_request_id: str) -> ModelResult:
        return await self.delegate.cancel(provider_request_id)

    def normalize_error(self, error: Exception) -> ProviderInvocationError:
        return self.delegate.normalize_error(error)


class _FixedRegistry:
    def __init__(self, adapters: tuple[ProviderAdapter, ...]) -> None:
        self._adapters = adapters
        self._by_key = {adapter.descriptor.key: adapter for adapter in adapters}

    def adapters(self) -> tuple[ProviderAdapter, ...]:
        return self._adapters

    def get(self, provider: str, model: str) -> ProviderAdapter:
        return self._by_key[f"{provider}:{model}"]


class RegistryAwareModelRouter(ModelRouter):
    """Routes with one immutable Registry snapshot and policy view per request."""

    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        health: ProviderHealthRegistry,
        capability_registry: CapabilityRegistry,
        policy_resolver: ModelPolicyResolver | None = None,
    ) -> None:
        super().__init__(
            registry=registry,
            health=health,
            policy_resolver=policy_resolver,
        )
        self.capability_registry = capability_registry

    async def route(self, request: ModelRequest) -> RoutingDecision:
        snapshot = self.capability_registry.snapshot()
        base_policy = self.policy_resolver.resolve(request.organization_id)
        policy = self._merged_policy(request, snapshot, base_policy)
        adapters, registry_rejected = self._snapshot_adapters(
            request,
            snapshot,
            policy,
        )
        if not adapters:
            details = ";".join(
                f"{key}={','.join(reasons)}"
                for key, reasons in sorted(registry_rejected.items())
            )
            raise NoRouteError(f"no registry-eligible model route: {details}"[:2000])
        router = ModelRouter(
            registry=_FixedRegistry(adapters),
            health=self.health,
            policy_resolver=StaticModelPolicyResolver((policy,)),
        )
        decision = await router.route(
            self._apply_registry_preference(request, snapshot)
        )
        marker = (
            f"REGISTRY_SNAPSHOT:{snapshot.snapshot_id}",
            f"REGISTRY_VERSION:{snapshot.registry_version}",
            f"REGISTRY_HASH:{snapshot.content_hash[:16]}",
        )
        candidates = tuple(
            replace(candidate, reason_codes=candidate.reason_codes + marker)
            for candidate in decision.candidates
        )
        return RoutingDecision(
            request_id=decision.request_id,
            candidates=candidates,
            rejected={**registry_rejected, **decision.rejected},
        )

    def _snapshot_adapters(
        self,
        request: ModelRequest,
        snapshot: RegistrySnapshot,
        policy: OrganizationModelPolicy,
    ) -> tuple[tuple[ProviderAdapter, ...], dict[str, tuple[str, ...]]]:
        accepted: list[ProviderAdapter] = []
        rejected: dict[str, tuple[str, ...]] = {}
        requested_region = request.constraints.get("region")
        for adapter in self.registry.adapters():
            descriptor = adapter.descriptor
            model = snapshot.model(descriptor.key)
            if model is None:
                rejected[descriptor.key] = ("REGISTRY_MODEL_MISSING",)
                continue
            if not model.route_eligible:
                rejected[descriptor.key] = ("REGISTRY_ROUTE_DISABLED",)
                continue
            support = snapshot.support(descriptor.key, request.capability)
            if support == SupportLevel.UNKNOWN:
                rejected[descriptor.key] = ("REGISTRY_CAPABILITY_UNKNOWN",)
                continue
            if support == SupportLevel.NONE:
                rejected[descriptor.key] = ("REGISTRY_CAPABILITY_NONE",)
                continue
            if support == SupportLevel.PARTIAL:
                rejected[descriptor.key] = ("REGISTRY_CAPABILITY_PARTIAL",)
                continue
            if requested_region:
                if not model.regions:
                    rejected[descriptor.key] = ("REGISTRY_REGION_UNKNOWN",)
                    continue
                if str(requested_region) not in model.regions:
                    rejected[descriptor.key] = ("REGISTRY_REGION_UNAVAILABLE",)
                    continue
            if policy.allowed_regions:
                if not model.regions:
                    rejected[descriptor.key] = ("REGISTRY_REGION_UNKNOWN",)
                    continue
                if not set(model.regions).intersection(policy.allowed_regions):
                    rejected[descriptor.key] = ("REGISTRY_ORG_REGION_MISMATCH",)
                    continue
            quality = snapshot.quality_score(descriptor.key, request.capability)
            projected = ProviderModel(
                provider=model.provider,
                model=model.model,
                capabilities=frozenset({request.capability}),
                quality_score=(
                    quality if quality is not None else descriptor.quality_score
                ),
                latency_class=descriptor.latency_class,
                regions=frozenset(model.regions),
                supports_streaming=descriptor.supports_streaming,
                supports_async=descriptor.supports_async,
            )
            accepted.append(_RegistryAdapter(adapter, projected))
        return tuple(accepted), rejected

    def _merged_policy(
        self,
        request: ModelRequest,
        snapshot: RegistrySnapshot,
        base: OrganizationModelPolicy,
    ) -> OrganizationModelPolicy:
        registry_policy = snapshot.organization_policy(request.organization_id)
        if registry_policy is None:
            return base
        allowed_regions = _intersect_or_other(
            base.allowed_regions,
            registry_policy.allowed_regions,
        )
        return OrganizationModelPolicy(
            organization_id=request.organization_id,
            allowed_providers=base.allowed_providers,
            denied_providers=base.denied_providers.union(
                registry_policy.disabled_providers
            ),
            denied_models=base.denied_models.union(registry_policy.denied_models),
            allowed_regions=allowed_regions,
            max_estimated_request_usd=base.max_estimated_request_usd,
        )

    def _apply_registry_preference(
        self,
        request: ModelRequest,
        snapshot: RegistrySnapshot,
    ) -> ModelRequest:
        if request.routing_hints.get("preferred_model"):
            return request
        policy = snapshot.organization_policy(request.organization_id)
        if policy is None or not policy.preferred_models:
            return request
        hints: dict[str, Any] = dict(request.routing_hints)
        hints["preferred_model"] = policy.preferred_models[0]
        return replace(request, routing_hints=hints)


def _intersect_or_other(
    left: frozenset[str],
    right: frozenset[str],
) -> frozenset[str]:
    if left and right:
        return left.intersection(right)
    return left or right
