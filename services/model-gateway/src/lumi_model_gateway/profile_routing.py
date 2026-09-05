from __future__ import annotations

import re
from collections.abc import Mapping

from .errors import NoRouteError
from .models import ModelRequest
from .ports import ProviderAdapter, ProviderHealthRegistry, ProviderRegistry
from .routing import ModelPolicyResolver, ModelRouter, OrganizationModelPolicy

_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")


class ModelProfileRouter(ModelRouter):
    """ModelRouter with server-owned logical profile to provider/model mapping.

    Agent Runtime can request a logical ``model_profile`` but never chooses a
    provider credential or bypasses NODE-22 policy. Unknown profiles fail
    closed instead of silently routing to a default model.
    """

    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        health: ProviderHealthRegistry,
        profile_routes: Mapping[str, frozenset[str]],
        policy_resolver: ModelPolicyResolver | None = None,
    ) -> None:
        super().__init__(
            registry=registry,
            health=health,
            policy_resolver=policy_resolver,
        )
        available = {adapter.descriptor.key for adapter in registry.adapters()}
        normalized: dict[str, frozenset[str]] = {}
        for profile, keys in profile_routes.items():
            if not _PROFILE.fullmatch(profile):
                raise ValueError("MODEL_PROFILE_NAME_INVALID")
            if not keys:
                raise ValueError(f"MODEL_PROFILE_EMPTY:{profile}")
            unknown = set(keys) - available
            if unknown:
                raise ValueError(
                    f"MODEL_PROFILE_ROUTE_UNKNOWN:{profile}:{','.join(sorted(unknown))}"
                )
            normalized[profile] = frozenset(keys)
        if not normalized:
            raise ValueError("MODEL_PROFILE_ROUTES_REQUIRED")
        self.profile_routes = normalized

    async def route(self, request: ModelRequest):  # type: ignore[no-untyped-def]
        profile = self._requested_profile(request)
        if profile is not None and profile not in self.profile_routes:
            raise NoRouteError(f"unknown model profile: {profile}")
        return await super().route(request)

    def _static_rejections(
        self,
        request: ModelRequest,
        policy: OrganizationModelPolicy,
        adapter: ProviderAdapter,
    ) -> list[str]:
        reasons = super()._static_rejections(request, policy, adapter)
        profile = self._requested_profile(request)
        if profile is not None:
            allowed = self.profile_routes.get(profile)
            if allowed is None or adapter.descriptor.key not in allowed:
                reasons.append("MODEL_PROFILE_MISMATCH")
        return reasons

    def _reason_codes(self, request: ModelRequest, adapter: ProviderAdapter) -> list[str]:
        reasons = super()._reason_codes(request, adapter)
        profile = self._requested_profile(request)
        if profile is not None and adapter.descriptor.key in self.profile_routes.get(
            profile,
            frozenset(),
        ):
            reasons.append("MODEL_PROFILE_MATCH")
        return reasons

    @staticmethod
    def _requested_profile(request: ModelRequest) -> str | None:
        raw = request.constraints.get("model_profile")
        if raw is None:
            return None
        if not isinstance(raw, str) or not _PROFILE.fullmatch(raw):
            raise ValueError("MODEL_PROFILE_REQUEST_INVALID")
        return raw
