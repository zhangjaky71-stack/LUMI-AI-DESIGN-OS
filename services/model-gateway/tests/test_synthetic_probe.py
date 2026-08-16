from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from lumi_model_gateway.errors import (
    ErrorCategory,
    ProviderAcceptance,
    ProviderCallError,
)
from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthPolicy,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_store import (
    MemoryHealthStateStore,
)
from lumi_model_gateway.synthetic_probe import (
    SyntheticProbeDefinition,
    SyntheticProbePolicy,
    SyntheticProbeRunner,
    SyntheticProbeStatus,
)


@dataclass
class ManualClock:
    value: float = 1_700_000_000.0

    def now(self) -> float:
        return self.value


def build_runner(
    policy: SyntheticProbePolicy,
) -> tuple[SyntheticProbeRunner, AdaptiveProviderHealthRegistry]:
    clock = ManualClock()
    health = AdaptiveProviderHealthRegistry(
        store=MemoryHealthStateStore(now=clock.now),
        clock=clock,
        policy=ProviderHealthPolicy(
            minimum_samples=1,
            max_samples=10,
            window_seconds=60,
            state_ttl_seconds=300,
            consecutive_failures_open=1,
        ),
    )
    return SyntheticProbeRunner(
        health=health,
        policy=policy,
    ), health


def definition(
    **overrides: object,
) -> SyntheticProbeDefinition:
    values: dict[str, object] = {
        "provider": "provider-a",
        "model": "model-a",
        "capability": "llm.reasoning",
        "enabled": True,
        "provider_terms_allowed": True,
        "side_effect_free": True,
        "estimated_cost_usd": Decimal("0"),
        "timeout_seconds": 1.0,
    }
    values.update(overrides)
    return SyntheticProbeDefinition(**values)  # type: ignore[arg-type]


def test_probe_is_disabled_by_default() -> None:
    runner, _ = build_runner(SyntheticProbePolicy())
    called = 0

    async def probe() -> None:
        nonlocal called
        called += 1

    result = asyncio.run(runner.run_once(definition(), probe))
    assert result.status is SyntheticProbeStatus.SKIPPED
    assert result.reason == "probe_disabled"
    assert called == 0


def test_probe_requires_terms_side_effect_and_cost_policy() -> None:
    runner, _ = build_runner(
        SyntheticProbePolicy(enabled=True)
    )

    async def probe() -> None:
        raise AssertionError("denied probe must never run")

    terms = asyncio.run(
        runner.run_once(
            definition(provider_terms_allowed=False),
            probe,
        )
    )
    assert terms.reason == "provider_terms_not_verified"

    side_effect = asyncio.run(
        runner.run_once(
            definition(side_effect_free=False),
            probe,
        )
    )
    assert side_effect.reason == "probe_not_side_effect_free"

    paid = asyncio.run(
        runner.run_once(
            definition(estimated_cost_usd=Decimal("0.001")),
            probe,
        )
    )
    assert paid.reason == "probe_cost_above_policy"


def test_probe_internal_bug_does_not_poison_provider_health() -> None:
    runner, health = build_runner(
        SyntheticProbePolicy(enabled=True)
    )

    async def broken_probe() -> None:
        raise RuntimeError("our probe implementation bug")

    result = asyncio.run(
        runner.run_once(definition(), broken_probe)
    )
    assert result.status is SyntheticProbeStatus.FAILED
    assert result.reason == "probe_internal_error"
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.UNKNOWN
    assert snapshot.sample_count == 0


def test_normalized_provider_probe_failure_opens_health() -> None:
    runner, health = build_runner(
        SyntheticProbePolicy(enabled=True)
    )

    async def provider_failure() -> None:
        raise ProviderCallError(
            ErrorCategory.PROVIDER_5XX,
            "provider unavailable",
            provider="provider-a",
            acceptance=ProviderAcceptance.NOT_ACCEPTED,
        )

    result = asyncio.run(
        runner.run_once(definition(), provider_failure)
    )
    assert result.status is SyntheticProbeStatus.FAILED
    assert result.reason == "probe_provider_error:provider_5xx"
    assert health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    ).state is ProviderHealthState.OPEN_CIRCUIT


def test_explicit_paid_probe_requires_both_cost_limit_and_opt_in() -> None:
    runner, _ = build_runner(
        SyntheticProbePolicy(
            enabled=True,
            max_estimated_cost_usd=Decimal("0.01"),
            allow_paid_probes=False,
        )
    )

    async def probe() -> None:
        return None

    result = asyncio.run(
        runner.run_once(
            definition(estimated_cost_usd=Decimal("0.001")),
            probe,
        )
    )
    assert result.status is SyntheticProbeStatus.SKIPPED
    assert result.reason == "paid_probe_not_allowed"
