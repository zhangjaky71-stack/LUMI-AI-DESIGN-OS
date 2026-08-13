from __future__ import annotations

import unittest

from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthPolicy,
    ProviderHealthState,
)


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ProviderHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = ManualClock()
        self.policy = ProviderHealthPolicy(
            window_seconds=60,
            max_samples=20,
            minimum_samples=4,
            degraded_failure_rate=0.25,
            open_failure_rate=0.50,
            consecutive_failures_open=3,
            open_cooldown_seconds=10,
            half_open_successes_to_close=2,
            half_open_max_probes=1,
            degraded_latency_ms=1_000,
        )
        self.health = AdaptiveProviderHealthRegistry(
            policy=self.policy,
            clock=self.clock,
        )

    def test_initial_health_is_healthy_and_client_error_is_ignored(self) -> None:
        initial = self.health.snapshot("provider", "model")
        self.assertEqual(initial.state, ProviderHealthState.HEALTHY)
        self.assertEqual(initial.score, 100)
        self.health.record_failure(
            "provider",
            "model",
            error_category="invalid_request",
            latency_ms=10,
        )
        after = self.health.snapshot("provider", "model")
        self.assertEqual(after.sample_count, 0)
        self.assertEqual(after.state, ProviderHealthState.HEALTHY)

    def test_failure_rate_degrades_and_consecutive_failures_open(self) -> None:
        for _ in range(3):
            self.health.record_success("provider", "model", latency_ms=100)
        self.health.record_failure(
            "provider",
            "model",
            error_category="timeout",
            latency_ms=500,
        )
        degraded = self.health.snapshot("provider", "model")
        self.assertEqual(degraded.state, ProviderHealthState.DEGRADED)
        self.assertEqual(degraded.failure_rate, 0.25)
        self.assertGreater(degraded.score, 0)
        self.assertLessEqual(degraded.score, 70)

        self.health.record_failure(
            "provider",
            "model",
            error_category="provider_503",
            latency_ms=500,
        )
        self.health.record_failure(
            "provider",
            "model",
            error_category="provider_503",
            latency_ms=500,
        )
        opened = self.health.snapshot("provider", "model")
        self.assertEqual(opened.state, ProviderHealthState.OPEN)
        self.assertEqual(opened.score, 0)
        self.assertFalse(self.health.is_available("provider", "model"))

    def test_retry_after_opens_immediately_and_extends_cooldown(self) -> None:
        self.health.record_failure(
            "provider",
            "model",
            error_category="rate_limited",
            retry_after_seconds=45,
        )
        opened = self.health.snapshot("provider", "model")
        self.assertEqual(opened.state, ProviderHealthState.OPEN)
        self.assertEqual(opened.open_until_monotonic, 45.0)
        self.clock.advance(20)
        self.assertEqual(
            self.health.snapshot("provider", "model").state,
            ProviderHealthState.OPEN,
        )

    def test_half_open_allows_one_probe_and_two_successes_close(self) -> None:
        for _ in range(3):
            self.health.record_failure(
                "provider",
                "model",
                error_category="timeout",
            )
        self.assertEqual(
            self.health.snapshot("provider", "model").state,
            ProviderHealthState.OPEN,
        )
        self.clock.advance(10)
        half_open = self.health.snapshot("provider", "model")
        self.assertEqual(half_open.state, ProviderHealthState.HALF_OPEN)
        self.assertEqual(half_open.score, 20)
        self.assertTrue(self.health.acquire_probe("provider", "model"))
        self.assertFalse(self.health.acquire_probe("provider", "model"))

        self.health.record_success("provider", "model", latency_ms=100)
        first = self.health.snapshot("provider", "model")
        self.assertEqual(first.state, ProviderHealthState.HALF_OPEN)
        self.assertEqual(first.half_open_successes, 1)
        self.assertTrue(self.health.acquire_probe("provider", "model"))
        self.health.record_success("provider", "model", latency_ms=100)
        closed = self.health.snapshot("provider", "model")
        self.assertEqual(closed.state, ProviderHealthState.HEALTHY)
        self.assertEqual(closed.score, 100)
        self.assertEqual(closed.sample_count, 0)

    def test_half_open_failure_reopens(self) -> None:
        for _ in range(3):
            self.health.record_failure(
                "provider",
                "model",
                error_category="timeout",
            )
        self.clock.advance(10)
        self.assertTrue(self.health.acquire_probe("provider", "model"))
        self.health.record_failure(
            "provider",
            "model",
            error_category="provider_500",
        )
        reopened = self.health.snapshot("provider", "model")
        self.assertEqual(reopened.state, ProviderHealthState.OPEN)
        self.assertEqual(reopened.open_until_monotonic, 20.0)

    def test_latency_p95_can_degrade_without_failures(self) -> None:
        for latency in (100, 100, 100, 1_500):
            self.health.record_success("provider", "model", latency_ms=latency)
        snapshot = self.health.snapshot("provider", "model")
        self.assertEqual(snapshot.state, ProviderHealthState.DEGRADED)
        self.assertEqual(snapshot.failure_rate, 0.0)
        self.assertEqual(snapshot.latency_p95_ms, 1_500)


if __name__ == "__main__":
    unittest.main()
