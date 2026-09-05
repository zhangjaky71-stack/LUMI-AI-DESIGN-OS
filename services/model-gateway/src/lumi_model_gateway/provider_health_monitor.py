from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import TelemetryEvent
from .provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthSnapshot,
    ProviderHealthState,
)


@dataclass(frozen=True, slots=True)
class ProviderHealthTransition:
    provider: str
    model: str
    previous_state: ProviderHealthState
    current_state: ProviderHealthState
    score: int
    sample_count: int
    failure_rate: float
    latency_p95_ms: int | None
    trace_id: str | None = None
    error_category: str | None = None


class ProviderHealthTransitionSink(Protocol):
    def emit(self, transition: ProviderHealthTransition) -> None: ...


@dataclass(slots=True)
class MemoryProviderHealthTransitionSink:
    events: list[ProviderHealthTransition] = field(default_factory=list)

    def emit(self, transition: ProviderHealthTransition) -> None:
        self.events.append(transition)


class ProviderHealthMonitor:
    """Converts existing Model Gateway telemetry into health observations."""

    def __init__(
        self,
        registry: AdaptiveProviderHealthRegistry,
        *,
        transition_sink: ProviderHealthTransitionSink | None = None,
    ) -> None:
        self.registry = registry
        self.transition_sink = transition_sink

    def observe(
        self,
        event: TelemetryEvent,
        *,
        retry_after_seconds: float | None = None,
    ) -> ProviderHealthSnapshot:
        before = self.registry.snapshot(event.provider, event.model)
        self.registry.record_telemetry(
            event,
            retry_after_seconds=retry_after_seconds,
        )
        after = self.registry.snapshot(event.provider, event.model)
        if self.transition_sink is not None and before.state != after.state:
            self.transition_sink.emit(
                ProviderHealthTransition(
                    provider=event.provider,
                    model=event.model,
                    previous_state=before.state,
                    current_state=after.state,
                    score=after.score,
                    sample_count=after.sample_count,
                    failure_rate=after.failure_rate,
                    latency_p95_ms=after.latency_p95_ms,
                    trace_id=event.trace_id,
                    error_category=event.error_category,
                )
            )
        return after
