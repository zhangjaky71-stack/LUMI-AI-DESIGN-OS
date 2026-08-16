from __future__ import annotations

from dataclasses import dataclass

from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    MemoryProviderHealthAuditSink,
    ProviderHealthPolicy,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_store import (
    MemoryHealthStateStore,
)


@dataclass
class ManualClock:
    value: float = 1_700_000_000.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def build_health(
    *,
    clock: ManualClock | None = None,
    audit: MemoryProviderHealthAuditSink | None = None,
    consecutive_failures_open: int = 3,
) -> tuple[
    AdaptiveProviderHealthRegistry,
    ManualClock,
    MemoryHealthStateStore,
]:
    clock = clock or ManualClock()
    store = MemoryHealthStateStore(now=clock.now)
    health = AdaptiveProviderHealthRegistry(
        store=store,
        clock=clock,
        audit_sink=audit,
        policy=ProviderHealthPolicy(
            window_seconds=60,
            state_ttl_seconds=300,
            minimum_samples=3,
            max_samples=20,
            degraded_failure_rate=0.34,
            open_failure_rate=0.67,
            degraded_rate_limit_rate=0.34,
            open_rate_limit_rate=0.67,
            degraded_timeout_rate=0.34,
            open_timeout_rate=0.67,
            consecutive_failures_open=consecutive_failures_open,
            open_cooldown_seconds=10,
            recovering_successes_to_close=2,
            recovering_max_probes=1,
            degraded_latency_p95_ms=100,
            degraded_queue_completion_p95_ms=1_000,
        ),
    )
    return health, clock, store


def test_initial_state_is_unknown_and_conservative() -> None:
    health, _, _ = build_health()
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.UNKNOWN
    assert snapshot.routable is True
    assert 0 < snapshot.score < 100


def test_minimum_sample_prevents_single_failure_from_declaring_health() -> None:
    health, _, _ = build_health()
    health.record_failure(
        "provider-a",
        "model-a",
        "provider_5xx",
        capability="llm.reasoning",
    )
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.UNKNOWN


def test_provider_5xx_burst_opens_circuit() -> None:
    health, _, _ = build_health()
    for _ in range(3):
        health.record_failure(
            "provider-a",
            "model-a",
            "provider_5xx",
            capability="llm.reasoning",
        )
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.OPEN_CIRCUIT
    assert snapshot.score == 0
    assert snapshot.routable is False


def test_user_and_local_errors_do_not_pollute_provider_health() -> None:
    health, _, _ = build_health(consecutive_failures_open=1)
    for category in (
        "invalid_request",
        "user_content_policy_block",
        "budget_exceeded",
        "hard_constraint_invalid",
        "unknown",
    ):
        health.record_failure(
            "provider-a",
            "model-a",
            category,
            capability="llm.reasoning",
        )
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.UNKNOWN
    assert snapshot.sample_count == 0


def test_retry_after_rate_limit_opens_through_requested_cooldown() -> None:
    health, clock, _ = build_health()
    health.record_failure(
        "provider-a",
        "model-a",
        "rate_limit",
        capability="llm.reasoning",
        retry_after_seconds=25,
    )
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.OPEN_CIRCUIT
    assert snapshot.open_until_epoch is not None
    assert snapshot.open_until_epoch >= clock.now() + 25


def test_half_open_recovery_has_single_probe_and_closes() -> None:
    health, clock, _ = build_health()
    for _ in range(3):
        health.record_failure(
            "provider-a",
            "model-a",
            "provider_5xx",
            capability="llm.reasoning",
        )
    clock.advance(11)
    recovering = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert recovering.state is ProviderHealthState.RECOVERING
    assert health.acquire_probe(
        "provider-a",
        "model-a",
        capability="llm.reasoning",
    )
    assert not health.acquire_probe(
        "provider-a",
        "model-a",
        capability="llm.reasoning",
    )
    health.record_success(
        "provider-a",
        "model-a",
        20,
        capability="llm.reasoning",
    )
    health.release_probe(
        "provider-a",
        "model-a",
        capability="llm.reasoning",
    )
    assert health.acquire_probe(
        "provider-a",
        "model-a",
        capability="llm.reasoning",
    )
    health.record_success(
        "provider-a",
        "model-a",
        20,
        capability="llm.reasoning",
    )
    health.release_probe(
        "provider-a",
        "model-a",
        capability="llm.reasoning",
    )
    assert health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    ).state is ProviderHealthState.HEALTHY


def test_capability_failure_does_not_open_sibling_endpoint() -> None:
    health, _, _ = build_health(consecutive_failures_open=2)
    for _ in range(2):
        health.record_failure(
            "provider-a",
            "shared-model",
            "capability_temp_unavailable",
            capability="video.text_to_video",
        )
    video = health.detailed_snapshot(
        "provider-a",
        "shared-model",
        "video.text_to_video",
    )
    llm = health.detailed_snapshot(
        "provider-a",
        "shared-model",
        "llm.reasoning",
    )
    assert video.state is ProviderHealthState.OPEN_CIRCUIT
    assert llm.state is ProviderHealthState.UNKNOWN
    assert llm.routable is True


def test_latency_and_queue_completion_can_degrade_independently() -> None:
    health, _, _ = build_health()
    for latency in (20, 30, 200):
        health.record_success(
            "provider-a",
            "model-a",
            latency,
            capability="llm.reasoning",
        )
    assert health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    ).state is ProviderHealthState.DEGRADED

    queue_health, _, _ = build_health()
    queue_health.record_queue_completion(
        "provider-a",
        "model-a",
        2_000,
        capability="video.text_to_video",
    )
    queue = queue_health.detailed_snapshot(
        "provider-a",
        "model-a",
        "video.text_to_video",
    )
    assert queue.state is ProviderHealthState.DEGRADED
    assert queue.queue_completion_p95_ms == 2_000


def test_manual_disable_requires_audit_and_expires_by_policy_ttl() -> None:
    audit = MemoryProviderHealthAuditSink()
    health, clock, _ = build_health(audit=audit)
    health.disable(
        "provider-a",
        actor_id="admin-1",
        reason="provider incident",
        ttl_seconds=5,
    )
    disabled = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert disabled.state is ProviderHealthState.DISABLED
    assert disabled.routable is False
    assert audit.events[-1].action == "force_disabled"
    assert audit.events[-1].reason == "provider incident"

    clock.advance(6)
    after_expiry = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert after_expiry.state is ProviderHealthState.UNKNOWN


def test_manual_override_fails_closed_without_audit_sink() -> None:
    health, _, _ = build_health()
    try:
        health.disable(
            "provider-a",
            actor_id="admin-1",
            reason="incident",
            ttl_seconds=60,
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "PROVIDER_HEALTH_MANUAL_OVERRIDE_AUDIT_REQUIRED"
        )
    else:
        raise AssertionError("unaudited override was accepted")


def test_redis_style_state_reset_returns_unknown_not_healthy() -> None:
    health, _, store = build_health()
    for _ in range(3):
        health.record_success(
            "provider-a",
            "model-a",
            10,
            capability="llm.reasoning",
        )
    assert health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    ).state is ProviderHealthState.HEALTHY
    store.clear()
    reset = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert reset.state is ProviderHealthState.UNKNOWN
