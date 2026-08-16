from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from time import monotonic

from .errors import ProviderCallError
from .provider_health import AdaptiveProviderHealthRegistry


class SyntheticProbeStatus(StrEnum):
    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SyntheticProbeDefinition:
    provider: str
    model: str
    capability: str
    enabled: bool = False
    provider_terms_allowed: bool = False
    side_effect_free: bool = False
    estimated_cost_usd: Decimal = Decimal("0")
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.provider or not self.model or not self.capability:
            raise ValueError(
                "PROVIDER_HEALTH_PROBE_IDENTITY_REQUIRED"
            )
        if self.estimated_cost_usd < 0:
            raise ValueError("PROVIDER_HEALTH_PROBE_COST_INVALID")
        if self.timeout_seconds <= 0:
            raise ValueError(
                "PROVIDER_HEALTH_PROBE_TIMEOUT_INVALID"
            )


@dataclass(frozen=True, slots=True)
class SyntheticProbePolicy:
    enabled: bool = False
    allow_paid_probes: bool = False
    max_estimated_cost_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.max_estimated_cost_usd < 0:
            raise ValueError(
                "PROVIDER_HEALTH_PROBE_POLICY_COST_INVALID"
            )


@dataclass(frozen=True, slots=True)
class SyntheticProbeResult:
    status: SyntheticProbeStatus
    reason: str
    latency_ms: int | None = None


ProbeCall = Callable[[], Awaitable[None]]


class SyntheticProbeRunner:
    """Runs only explicitly authorized probes; embeds no provider SDK."""

    def __init__(
        self,
        *,
        health: AdaptiveProviderHealthRegistry,
        policy: SyntheticProbePolicy | None = None,
    ) -> None:
        self.health = health
        self.policy = policy or SyntheticProbePolicy()

    async def run_once(
        self,
        definition: SyntheticProbeDefinition,
        probe: ProbeCall,
    ) -> SyntheticProbeResult:
        denied_reason = self._denied_reason(definition)
        if denied_reason is not None:
            return SyntheticProbeResult(
                SyntheticProbeStatus.SKIPPED,
                denied_reason,
            )
        if not self.health.acquire_probe(
            definition.provider,
            definition.model,
            capability=definition.capability,
        ):
            return SyntheticProbeResult(
                SyntheticProbeStatus.SKIPPED,
                "recovery_probe_capacity_unavailable",
            )

        started = monotonic()
        try:
            async with asyncio.timeout(
                definition.timeout_seconds
            ):
                await probe()
        except TimeoutError:
            latency_ms = int(
                (monotonic() - started) * 1000
            )
            self.health.record_failure(
                definition.provider,
                definition.model,
                "timeout",
                capability=definition.capability,
                latency_ms=latency_ms,
            )
            self.health.release_probe(
                definition.provider,
                definition.model,
                capability=definition.capability,
            )
            return SyntheticProbeResult(
                SyntheticProbeStatus.FAILED,
                "probe_timeout",
                latency_ms,
            )
        except ProviderCallError as exc:
            latency_ms = int(
                (monotonic() - started) * 1000
            )
            self.health.record_failure(
                definition.provider,
                definition.model,
                exc.category.value,
                capability=definition.capability,
                latency_ms=latency_ms,
                retry_after_seconds=exc.retry_after_seconds,
            )
            self.health.release_probe(
                definition.provider,
                definition.model,
                capability=definition.capability,
            )
            return SyntheticProbeResult(
                SyntheticProbeStatus.FAILED,
                f"probe_provider_error:{exc.category.value}",
                latency_ms,
            )
        except Exception:
            # Probe implementation/configuration errors are ours, not Provider evidence.
            latency_ms = int(
                (monotonic() - started) * 1000
            )
            self.health.release_probe(
                definition.provider,
                definition.model,
                capability=definition.capability,
            )
            return SyntheticProbeResult(
                SyntheticProbeStatus.FAILED,
                "probe_internal_error",
                latency_ms,
            )

        latency_ms = int((monotonic() - started) * 1000)
        self.health.record_success(
            definition.provider,
            definition.model,
            latency_ms,
            capability=definition.capability,
        )
        self.health.release_probe(
            definition.provider,
            definition.model,
            capability=definition.capability,
        )
        return SyntheticProbeResult(
            SyntheticProbeStatus.SUCCEEDED,
            "probe_succeeded",
            latency_ms,
        )

    def _denied_reason(
        self,
        definition: SyntheticProbeDefinition,
    ) -> str | None:
        if not self.policy.enabled or not definition.enabled:
            return "probe_disabled"
        if not definition.provider_terms_allowed:
            return "provider_terms_not_verified"
        if not definition.side_effect_free:
            return "probe_not_side_effect_free"
        if (
            definition.estimated_cost_usd
            > self.policy.max_estimated_cost_usd
        ):
            return "probe_cost_above_policy"
        if (
            definition.estimated_cost_usd > 0
            and not self.policy.allow_paid_probes
        ):
            return "paid_probe_not_allowed"
        return None
