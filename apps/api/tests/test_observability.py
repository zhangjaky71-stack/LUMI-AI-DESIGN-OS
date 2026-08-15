from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.observability import (
    BoundedMetrics,
    ObservabilityConfig,
    apply_observability,
    current_correlation,
    safe_log_record,
)
from lumi_api.observability.core import new_correlation_context, parse_traceparent


def test_valid_traceparent_is_propagated() -> None:
    trace_id = "a" * 32
    parent_span_id = "b" * 16
    context = new_correlation_context(
        request_id="req-1",
        correlation_id="corr-1",
        traceparent=f"00-{trace_id}-{parent_span_id}-01",
    )
    assert context.trace_id == trace_id
    assert context.request_id == "req-1"
    assert context.correlation_id == "corr-1"
    assert context.traceparent.startswith(f"00-{trace_id}-")


def test_invalid_traceparent_fails_closed_to_new_trace() -> None:
    assert parse_traceparent("00-not-a-trace-not-a-span-01") is None
    context = new_correlation_context(
        request_id=None,
        correlation_id=None,
        traceparent="00-not-a-trace-not-a-span-01",
    )
    assert len(context.trace_id) == 32
    assert context.trace_id != "0" * 32


def test_untrusted_request_ids_are_not_reflected() -> None:
    context = new_correlation_context(
        request_id="bad id with spaces\nheader: injected",
        correlation_id="../../tenant-secret",
        traceparent=None,
    )
    assert context.request_id != "bad id with spaces\nheader: injected"
    assert context.correlation_id != "../../tenant-secret"


def test_safe_log_record_drops_content_and_secret_fields() -> None:
    record = safe_log_record(
        level="info",
        service="api",
        environment="test",
        event="agent.completed",
        fields={
            "prompt": "do not log me",
            "authorization": "Bearer secret",
            "signed_url": "https://storage.example/file?token=secret",
            "status": "ok",
            "error": "api_key=supersecret",
        },
    )
    assert "prompt" not in record
    assert "authorization" not in record
    assert "signed_url" not in record
    assert record["status"] == "ok"
    assert "supersecret" not in str(record["error"])


def test_metric_labels_reject_high_cardinality_dimensions() -> None:
    metrics = BoundedMetrics()
    with pytest.raises(
        ValueError,
        match="OBSERVABILITY_HIGH_CARDINALITY_LABEL_FORBIDDEN:organization_id",
    ):
        metrics.increment(
            "lumi_agent_runs_total",
            labels={"organization_id": "org-secret"},
        )


def test_metrics_render_bounded_http_series() -> None:
    metrics = BoundedMetrics()
    metrics.observe_http(
        method="GET",
        route="/projects/{project_id}",
        status_code=200,
        duration=0.2,
    )
    rendered = metrics.render_prometheus()
    assert "lumi_http_requests_total" in rendered
    assert 'route="/projects/{project_id}"' in rendered
    assert "project_id=" not in rendered
    assert "lumi_http_request_duration_seconds_bucket" in rendered


def test_middleware_adds_correlation_headers_and_metrics() -> None:
    app = FastAPI()
    metrics = apply_observability(
        app,
        ObservabilityConfig(service_name="test-api", environment="test"),
    )

    @app.get("/projects/{project_id}")
    def project(project_id: str) -> dict[str, str]:
        assert current_correlation() is not None
        return {"project_id": project_id}

    client = TestClient(app)
    response = client.get(
        "/projects/secret-project-123",
        headers={"x-request-id": "req-123", "x-correlation-id": "corr-123"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert response.headers["x-correlation-id"] == "corr-123"
    assert response.headers["traceparent"].startswith("00-")

    rendered = metrics.render_prometheus()
    assert 'route="/projects/{project_id}"' in rendered
    assert "secret-project-123" not in rendered

    metrics_response = client.get("/internal/metrics")
    assert metrics_response.status_code == 200
    assert "lumi_http_requests_total" in metrics_response.text
    assert metrics.render_prometheus() == rendered


def test_telemetry_logging_failure_cannot_break_business_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    apply_observability(
        app,
        ObservabilityConfig(service_name="test-api", environment="test"),
    )

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    def explode(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("telemetry backend unavailable")

    monkeypatch.setattr("lumi_api.observability.middleware.safe_log_record", explode)
    response = TestClient(app).get("/ok")
    assert response.status_code == 200
