from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.models import (
    Capability,
    CostConfidence,
    CostEstimate,
    TelemetryEvent,
)
from lumi_model_gateway.telemetry import (
    MemoryCostTelemetrySink,
    ResilientCostTelemetrySink,
    project_model_telemetry,
)


def _event(*, error_category: str | None = None) -> TelemetryEvent:
    return TelemetryEvent(
        request_id=UUID("00000000-0000-0000-0000-000000000001"),
        organization_id=UUID("00000000-0000-0000-0000-000000000002"),
        operation_id=UUID("00000000-0000-0000-0000-000000000003"),
        capability=Capability.LLM_REASONING,
        provider="example-provider",
        model="example-model",
        routing_reason_codes=("capability_match",),
        attempt=1,
        fallback_index=0,
        retry_count=0,
        latency_ms=250,
        usage=None,
        cost=CostEstimate(
            amount_usd=Decimal("0.0123"),
            confidence=CostConfidence.EXACT,
        ),
        error_category=error_category,
        semantic_hash="a" * 64,
        trace_id="b" * 32,
        project_id=UUID("00000000-0000-0000-0000-000000000004"),
        task_id=UUID("00000000-0000-0000-0000-000000000005"),
        agent_run_id=UUID("00000000-0000-0000-0000-000000000006"),
        generation_id=UUID("00000000-0000-0000-0000-000000000007"),
        provider_request_id="provider-request-1",
    )


def test_resilient_sink_preserves_normal_recording() -> None:
    memory = MemoryCostTelemetrySink()
    sink = ResilientCostTelemetrySink(memory)
    event = _event()
    sink.record(event)
    assert memory.records == [event]


def test_resilient_sink_swallows_telemetry_backend_failure() -> None:
    class ExplodingSink:
        def record(self, event: TelemetryEvent) -> None:
            del event
            raise RuntimeError("telemetry backend unavailable")

    ResilientCostTelemetrySink(ExplodingSink()).record(_event())


def test_model_projection_keeps_tenant_ids_out_of_metric_labels() -> None:
    projection = project_model_telemetry(_event())
    assert projection.metric_labels == {
        "provider": "example-provider",
        "outcome": "success",
    }
    assert "organization_id" not in projection.metric_labels
    assert "project_id" not in projection.metric_labels
    assert str(projection.trace_attributes["lumi.organization_id"]).endswith("0002")
    assert str(projection.trace_attributes["lumi.project_id"]).endswith("0004")
    assert projection.latency_seconds == 0.25
    assert projection.cost_usd == Decimal("0.0123")


def test_model_projection_marks_errors_without_logging_payloads() -> None:
    projection = project_model_telemetry(_event(error_category="rate_limit"))
    assert projection.metric_labels["outcome"] == "error"
    assert projection.trace_attributes["error.type"] == "rate_limit"
    serialized = repr(projection)
    assert "prompt" not in serialized.lower()
    assert "output" not in serialized.lower()
