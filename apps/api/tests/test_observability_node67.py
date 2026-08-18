from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lumi_api.api.v1.errors import install_error_contract
from lumi_api.events.envelope import new_event
from lumi_api.events.outbox import project_to_outbox
from lumi_api.events.payloads import ProjectCreatedV1
from lumi_api.observability import (
    DeterministicSampler,
    LogLevel,
    MetricPoint,
    SafeLangSmithTracer,
    SafeTelemetry,
    SamplingDecision,
    SpanRecord,
    SpanStatus,
    StructuredLogRecord,
    current_telemetry_context,
    evaluate_error_budget,
    parse_traceparent,
    start_message_context,
    start_request_context,
)
from lumi_api.observability.slo import CORE_API_AVAILABILITY

ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")
NOW = datetime(2026, 8, 18, 11, 0, tzinfo=UTC)


class CapturingSink:
    def __init__(self) -> None:
        self.spans = []
        self.metrics = []
        self.logs = []

    def record_span(self, span) -> None:
        self.spans.append(span)

    def record_metric(self, metric) -> None:
        self.metrics.append(metric)

    def emit_log(self, record) -> None:
        self.logs.append(record)


class FailingSink:
    def record_span(self, span) -> None:
        raise RuntimeError("collector offline")

    def record_metric(self, metric) -> None:
        raise RuntimeError("collector offline")

    def emit_log(self, record) -> None:
        raise RuntimeError("collector offline")


class FailingLangSmith:
    def emit_agent_trace(self, **kwargs) -> None:
        raise RuntimeError("langsmith offline")


def test_traceparent_parser_rejects_zero_ids_and_invalid_version() -> None:
    parsed = parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    assert parsed is not None
    assert parsed.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    with pytest.raises(ValueError, match="ZERO_ID_FORBIDDEN"):
        parse_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01")
    with pytest.raises(ValueError, match="VERSION_INVALID"):
        parse_traceparent("ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")


def test_request_context_continues_trace_with_new_server_span() -> None:
    incoming = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    with start_request_context(
        request_id="request-1",
        correlation_id="corr-1",
        traceparent=incoming,
        tracestate="vendor=value",
    ) as context:
        assert context.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert context.parent_span_id == "00f067aa0ba902b7"
        assert context.span_id != context.parent_span_id
        assert context.tracestate == "vendor=value"


def test_message_context_creates_child_span_from_event_traceparent() -> None:
    with start_request_context(request_id="request-1", correlation_id="corr-1") as producer:
        event_traceparent = producer.traceparent
        with start_message_context(
            request_id="request-1",
            correlation_id="corr-1",
            traceparent=event_traceparent,
            tracestate=None,
            fallback_request_id="event-1",
        ) as consumer:
            assert consumer.trace_id == producer.trace_id
            assert consumer.parent_span_id == producer.span_id
            assert consumer.span_id != producer.span_id


def test_event_and_outbox_inherit_current_request_trace_context() -> None:
    with start_request_context(request_id="request-9", correlation_id="corr-9") as context:
        event = new_event(
            event_type="lumi.project.created.v1",
            organization_id=ORG,
            aggregate_type="project",
            aggregate_id=PROJECT,
            producer="lumi.api",
            payload=ProjectCreatedV1(
                project_id=PROJECT,
                workspace_id=WORKSPACE,
                project_version=1,
            ),
        )
        assert event.request_id == "request-9"
        assert event.correlation_id == "corr-9"
        assert event.traceparent == context.traceparent
        projection = project_to_outbox(event)
        assert projection.envelope_json["request_id"] == "request-9"
        assert projection.envelope_json["correlation_id"] == "corr-9"
        assert projection.envelope_json["traceparent"] == context.traceparent


def test_safe_telemetry_swallow_sink_failures() -> None:
    telemetry = SafeTelemetry(FailingSink())
    span = SpanRecord(
        name="test.span",
        trace_id="1" * 32,
        span_id="2" * 16,
        status=SpanStatus.ERROR,
        started_at=NOW,
        ended_at=NOW,
    )
    metric = MetricPoint(
        name="http.server.duration_ms",
        value=1.0,
        unit="ms",
        recorded_at=NOW,
        attributes={"service": "lumi-api"},
    )
    record = StructuredLogRecord(
        level=LogLevel.ERROR,
        event="test.failed",
        message="Test failed.",
        occurred_at=NOW,
    )
    telemetry.record_span(span)
    telemetry.record_metric(metric)
    telemetry.emit_log(record)
    assert telemetry.dropped_spans == 1
    assert telemetry.dropped_metrics == 1
    assert telemetry.dropped_logs == 1


def test_langsmith_outage_never_raises_into_business_code() -> None:
    tracer = SafeLangSmithTracer(FailingLangSmith())
    emitted = tracer.emit_agent_trace(
        trace_id="1" * 32,
        run_name="designer-agent",
        attributes={"agent_version": "v1"},
    )
    assert emitted is False
    assert tracer.dropped == 1


def test_metric_cardinality_guard_rejects_tenant_and_run_ids() -> None:
    with pytest.raises(ValueError, match="HIGH_CARDINALITY_ATTRIBUTE"):
        MetricPoint(
            name="agent.run.duration_ms",
            value=2.0,
            unit="ms",
            recorded_at=NOW,
            attributes={"organization_id": str(ORG)},
        )
    with pytest.raises(ValueError, match="HIGH_CARDINALITY_ATTRIBUTE"):
        MetricPoint(
            name="agent.run.duration_ms",
            value=2.0,
            unit="ms",
            recorded_at=NOW,
            attributes={"agent_run_id": "run-1"},
        )


def test_structured_log_rejects_prompt_or_secret_fields() -> None:
    with pytest.raises(ValueError, match="SENSITIVE_ATTRIBUTE_FORBIDDEN"):
        StructuredLogRecord(
            level=LogLevel.INFO,
            event="agent.completed",
            message="Agent completed.",
            occurred_at=NOW,
            fields={"prompt": "private user prompt"},
        )
    with pytest.raises(ValueError, match="SECRET_ATTRIBUTE_FORBIDDEN"):
        StructuredLogRecord(
            level=LogLevel.INFO,
            event="agent.completed",
            message="Agent completed.",
            occurred_at=NOW,
            fields={"note": "Bearer raw-token"},
        )


def test_sampler_never_drops_errors_or_critical_logs() -> None:
    sampler = DeterministicSampler(normal_sample_rate=0.0)
    assert sampler.decide(trace_id="1" * 32) is SamplingDecision.DROP
    assert sampler.decide(trace_id="1" * 32, span_status=SpanStatus.ERROR) is SamplingDecision.RECORD_AND_SAMPLE
    assert sampler.decide(trace_id="1" * 32, log_level=LogLevel.CRITICAL) is SamplingDecision.RECORD_AND_SAMPLE


def test_error_budget_math_uses_versioned_slo_target() -> None:
    snapshot = evaluate_error_budget(
        CORE_API_AVAILABILITY,
        total_events=100_000,
        bad_events=50,
    )
    assert snapshot.allowed_bad_events == pytest.approx(100.0)
    assert snapshot.budget_remaining_ratio == pytest.approx(0.5)
    assert snapshot.burn_ratio == pytest.approx(0.5)


def test_http_middleware_emits_response_correlation_and_safe_records() -> None:
    app = FastAPI()
    sink = CapturingSink()
    app.state.telemetry = SafeTelemetry(sink)
    app.state.telemetry_sampler = DeterministicSampler(normal_sample_rate=1.0)
    install_error_contract(app)

    @app.get("/health/{kind}")
    def health(kind: str, request: Request):
        context = current_telemetry_context()
        assert context is not None
        return {"kind": kind, "trace_id": context.trace_id}

    incoming = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    with TestClient(app) as client:
        response = client.get(
            "/health/live",
            headers={
                "X-Request-ID": "request-http-1",
                "X-Correlation-ID": "corr-http-1",
                "traceparent": incoming,
            },
        )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-http-1"
    assert response.headers["X-Correlation-ID"] == "corr-http-1"
    outgoing = parse_traceparent(response.headers["traceparent"])
    assert outgoing is not None
    assert outgoing.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert len(sink.spans) == 1
    assert sink.spans[0].attributes["http.route"] == "/health/{kind}"
    assert len(sink.metrics) == 1
    assert "organization_id" not in sink.metrics[0].attributes
    assert len(sink.logs) == 1


def test_invalid_traceparent_fails_as_bounded_400_not_500() -> None:
    app = FastAPI()
    install_error_contract(app)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ok", headers={"traceparent": "not-a-traceparent"})
    assert response.status_code == 400
    assert response.json()["code"] == "observability_trace_context_invalid"
