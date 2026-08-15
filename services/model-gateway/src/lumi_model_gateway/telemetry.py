from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .models import TelemetryEvent


class TelemetryDelegate(Protocol):
    def record(self, event: TelemetryEvent) -> None: ...


class MemoryCostTelemetrySink:
    def __init__(self) -> None:
        self.records: list[TelemetryEvent] = []
        self._lock = threading.Lock()

    def record(self, event: TelemetryEvent) -> None:
        with self._lock:
            self.records.append(event)


class NullCostTelemetrySink:
    def record(self, event: TelemetryEvent) -> None:
        del event


class ResilientCostTelemetrySink:
    """Protect the paid model path from telemetry backend failures."""

    def __init__(self, delegate: TelemetryDelegate) -> None:
        self.delegate = delegate

    def record(self, event: TelemetryEvent) -> None:
        try:
            self.delegate.record(event)
        except Exception:
            # Observability is never allowed to turn a completed/failed provider call
            # into a different business outcome.
            return


@dataclass(frozen=True, slots=True)
class ModelTelemetryProjection:
    metric_labels: dict[str, str]
    trace_attributes: dict[str, str | int | float]
    latency_seconds: float
    cost_usd: Decimal | None


def project_model_telemetry(event: TelemetryEvent) -> ModelTelemetryProjection:
    """Project gateway telemetry without prompts, outputs, or tenant IDs as metric labels."""

    outcome = "error" if event.error_category else "success"
    metric_labels = {
        "provider": event.provider[:100],
        "outcome": outcome,
    }
    trace_attributes: dict[str, str | int | float] = {
        "lumi.request_id": str(event.request_id),
        "lumi.operation_id": str(event.operation_id),
        "lumi.organization_id": str(event.organization_id),
        "lumi.capability": event.capability.value,
        "gen_ai.system": event.provider[:100],
        "gen_ai.request.model": event.model[:255],
        "lumi.attempt": event.attempt,
        "lumi.fallback_index": event.fallback_index,
        "lumi.retry_count": event.retry_count,
    }
    optional_refs = {
        "lumi.project_id": event.project_id,
        "lumi.task_id": event.task_id,
        "lumi.agent_run_id": event.agent_run_id,
        "lumi.generation_id": event.generation_id,
        "gen_ai.response.id": event.provider_request_id,
        "lumi.trace_id": event.trace_id,
    }
    for key, value in optional_refs.items():
        if value is not None:
            trace_attributes[key] = str(value)
    if event.error_category:
        trace_attributes["error.type"] = event.error_category[:120]

    return ModelTelemetryProjection(
        metric_labels=metric_labels,
        trace_attributes=trace_attributes,
        latency_seconds=max(event.latency_ms, 0) / 1000.0,
        cost_usd=event.cost.amount_usd if event.cost else None,
    )
