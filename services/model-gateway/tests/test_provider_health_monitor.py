from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_model_gateway.models import Capability, TelemetryEvent
from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthPolicy,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_monitor import (
    MemoryProviderHealthTransitionSink,
    ProviderHealthMonitor,
)


class ProviderHealthMonitorTests(unittest.TestCase):
    def test_telemetry_drives_health_and_emits_only_state_transitions(self) -> None:
        registry = AdaptiveProviderHealthRegistry(
            policy=ProviderHealthPolicy(
                minimum_samples=1,
                consecutive_failures_open=1,
                open_failure_rate=1.0,
            )
        )
        sink = MemoryProviderHealthTransitionSink()
        monitor = ProviderHealthMonitor(registry, transition_sink=sink)
        event = TelemetryEvent(
            request_id=uuid4(),
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            provider="provider",
            model="model",
            routing_reason_codes=(),
            attempt=1,
            fallback_index=0,
            retry_count=0,
            latency_ms=500,
            usage=None,
            cost=None,
            error_category="provider_503",
            semantic_hash="a" * 64,
            trace_id="trace-1",
        )
        snapshot = monitor.observe(event)
        self.assertEqual(snapshot.state, ProviderHealthState.OPEN)
        self.assertEqual(len(sink.events), 1)
        transition = sink.events[0]
        self.assertEqual(transition.previous_state, ProviderHealthState.HEALTHY)
        self.assertEqual(transition.current_state, ProviderHealthState.OPEN)
        self.assertEqual(transition.trace_id, "trace-1")
        self.assertEqual(transition.error_category, "provider_503")

        monitor.observe(event)
        self.assertEqual(len(sink.events), 1)


if __name__ == "__main__":
    unittest.main()
