from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise SystemExit(f"NODE67_VALIDATION_FAILED:{label}:{needle}")


def forbid(haystack: str, needle: str, label: str) -> None:
    if needle in haystack:
        raise SystemExit(f"NODE67_VALIDATION_FAILED:{label}:{needle}")


def main() -> None:
    context = read("apps/api/src/lumi_api/observability/context.py")
    models = read("apps/api/src/lumi_api/observability/models.py")
    sampling = read("apps/api/src/lumi_api/observability/sampling.py")
    telemetry = read("apps/api/src/lumi_api/observability/telemetry.py")
    langsmith = read("apps/api/src/lumi_api/observability/langsmith.py")
    slo = read("apps/api/src/lumi_api/observability/slo.py")
    errors = read("apps/api/src/lumi_api/api/v1/errors.py")
    auth_guard = read("apps/api/src/lumi_api/api/v1/auth_guard.py")
    app = read("apps/api/src/lumi_api/api/v1/app.py")
    event_envelope = read("apps/api/src/lumi_api/events/envelope.py")
    outbox = read("apps/api/src/lumi_api/events/outbox.py")
    tests = read("apps/api/tests/test_observability_node67.py")
    boundary_tests = read("apps/api/tests/test_observability_security_boundary_node67.py")
    middleware_tests = read("apps/api/tests/test_observability_middleware_order_node67.py")
    event_tests = read("apps/api/tests/test_event_contract.py")

    node_doc = read("docs/nodes/NODE-67-OBSERVABILITY.md")
    report = read("reports/nodes/NODE-67/implementation.md")
    current_track = read("reports/nodes/NODE-67/current-track.md")
    gap_ledger = json.loads(read("reports/nodes/NODE-67/gap-ledger.json"))
    dashboard = json.loads(read("reports/nodes/NODE-67/dashboard-spec.json"))
    alerts = json.loads(read("reports/nodes/NODE-67/alert-policy.json"))
    slo_policy = json.loads(read("reports/nodes/NODE-67/slo-policy.json"))

    # Correlation contract: W3C headers are untrusted telemetry metadata. Invalid
    # trace state restarts/discards telemetry context instead of rejecting business.
    for marker in (
        "OBSERVABILITY_TRACEPARENT_INVALID",
        "OBSERVABILITY_TRACEPARENT_ZERO_ID_FORBIDDEN",
        "OBSERVABILITY_TRACESTATE_INVALID",
        "start_request_context",
        "start_message_context",
        "bind_business_refs",
    ):
        require(context, marker, f"correlation context {marker}")
    require(context, "Malformed trace context must", "trace context fail-open policy")
    require(context, "invalid traceparent restarts the trace", "traceparent restart policy")
    require(context, "invalid tracestate is discarded", "tracestate discard policy")
    require(context, 'r"^[a-z0-9][a-z0-9_*/@-]{0,255}$"', "W3C tracestate key grammar")
    require(context, 'char in {",", "="}', "W3C tracestate value grammar")
    require(context, 'version == "00" and len(normalized) != 55', "traceparent v00 length")
    require(context, 'version != "00" and len(normalized) > 55', "future traceparent version tolerance")
    require(context, '"request_id": self.request_id', "event request correlation fields")
    require(context, '"correlation_id": self.correlation_id', "event correlation id fields")
    require(context, '"traceparent": self.traceparent', "event traceparent fields")
    require(tests, "test_invalid_traceparent_restarts_trace_without_failing_business_request", "traceparent fail-open test")
    require(tests, "test_invalid_tracestate_is_discarded_without_breaking_valid_traceparent", "tracestate fail-open test")
    require(tests, "test_traceparent_parser_tolerates_additive_future_version_fields", "future traceparent version test")

    # HTTP ingress owns canonical telemetry IDs and uses route templates rather than raw ids.
    require(errors, 'request.headers.get("X-Correlation-ID")', "correlation header")
    require(errors, 'request.headers.get("traceparent")', "traceparent header")
    require(errors, 'response.headers["X-Request-ID"]', "request response header")
    require(errors, 'response.headers["X-Correlation-ID"]', "correlation response header")
    require(errors, 'response.headers["traceparent"]', "trace response header")
    require(errors, "Request/correlation/trace headers are telemetry metadata", "telemetry input fail-open policy")
    forbid(errors, "observability_trace_context_invalid", "telemetry metadata must not reject business requests")
    require(boundary_tests, "test_invalid_correlation_id_falls_back_to_canonical_request_id", "correlation fail-open test")
    require(errors, 'candidate = getattr(route, "path", None)', "route-template metric label")
    require(errors, 'name="http.server.duration_ms"', "HTTP duration metric")
    require(errors, 'event="http.request.completed"', "HTTP structured log")
    forbid(errors, "request.url.path,\n                    \"http.route\"", "raw path metric label")

    # Trace/correlation parsing may not swallow downstream business errors.
    require(boundary_tests, "test_business_value_error_is_not_reclassified_as_trace_context_error", "business error regression")
    require(middleware_tests, "test_downstream_value_error_is_not_misclassified_as_trace_context", "middleware business error regression")
    require(middleware_tests, "test_invalid_trace_does_not_short_circuit_authoritative_auth_semantics", "trace fail-open auth-order regression")

    # Auth uses middleware-generated ids, not raw trace headers.
    require(auth_guard, 'request_id = getattr(request.state, "request_id", "unassigned")', "auth canonical request id")
    require(auth_guard, "trace_id = telemetry_context.trace_id", "auth canonical trace id")
    require(auth_guard, "bind_business_refs(organization_id=organization_id)", "auth organization trace binding")
    forbid(auth_guard, 'request.headers.get("traceparent")', "auth raw traceparent reread")
    forbid(auth_guard, 'request.headers.get("X-Request-ID")', "auth raw request-id reread")

    # One canonical EventEnvelope / Outbox propagation path.
    require(event_envelope, "request_id: str | None", "event request id")
    require(event_envelope, "correlation_id: str | None", "event correlation id")
    require(event_envelope, "traceparent: str | None", "event traceparent")
    require(event_envelope, "tracestate: str | None", "event tracestate")
    require(event_envelope, "current_telemetry_context()", "event context inheritance")
    require(event_envelope, "parse_traceparent(value)", "event trace validation")
    require(outbox, "event.model_dump(mode=\"json\")", "outbox full envelope preservation")
    require(tests, "test_event_and_outbox_inherit_current_request_trace_context", "producer propagation test")
    require(tests, "test_message_context_creates_child_span_from_event_traceparent", "consumer child context test")
    require(event_tests, "correlation_id", "legacy event correlation contract")

    # Telemetry safety / cardinality.
    for sensitive in (
        "prompt",
        "content",
        "authorization",
        "token",
        "secret",
        "api_key",
        "signed_url",
        "reasoning",
    ):
        require(models, sensitive, f"sensitive telemetry marker {sensitive}")
    for low_card in (
        '"service"',
        '"http.method"',
        '"http.route"',
        '"http.status_class"',
        '"provider"',
        '"capability"',
        '"queue"',
        '"worker"',
    ):
        require(models, low_card, f"metric allowlist {low_card}")
    require(models, "OBSERVABILITY_METRIC_HIGH_CARDINALITY_ATTRIBUTE", "cardinality rejection")
    require(tests, "test_metric_cardinality_guard_rejects_tenant_and_run_ids", "cardinality test")
    require(tests, "test_structured_log_rejects_prompt_or_secret_fields", "log redaction test")

    # Exporter/vendor failure cannot fail business logic.
    require(telemetry, "except Exception:", "telemetry fail-open")
    require(telemetry, "self.dropped_spans += 1", "span drop evidence")
    require(telemetry, "self.dropped_metrics += 1", "metric drop evidence")
    require(telemetry, "self.dropped_logs += 1", "log drop evidence")
    require(langsmith, "except Exception:", "LangSmith fail-open")
    require(langsmith, "self.dropped += 1", "LangSmith drop evidence")
    require(tests, "test_safe_telemetry_swallow_sink_failures", "telemetry outage test")
    require(tests, "test_langsmith_outage_never_raises_into_business_code", "LangSmith outage test")

    # Sampling / SLO.
    require(sampling, "span_status is SpanStatus.ERROR", "error 100% sample")
    require(sampling, "LogLevel.ERROR", "error log 100% sample")
    require(sampling, "LogLevel.CRITICAL", "critical log 100% sample")
    require(tests, "test_sampler_never_drops_errors_or_critical_logs", "sampling test")
    require(slo, 'key="core_api.availability"', "API SLO")
    require(slo, "target=0.999", "API availability target")
    require(slo, 'key="paid_side_effects.no_duplicate"', "paid-side-effect SLO")
    require(tests, "test_error_budget_math_uses_versioned_slo_target", "error budget test")

    # Structured logging is real; traces/metrics remain explicitly uncomposed.
    require(telemetry, "class PythonJsonLoggingSink", "JSON logging sink")
    require(telemetry, "json.dumps", "JSON logging serialization")
    require(app, "SafeTelemetry(PythonJsonLoggingSink())", "API logging composition")
    require(app, "DeterministicSampler(normal_sample_rate=0.10)", "API sampler composition")
    require(report, "does **not** currently claim", "explicit non-claims")
    require(report, "OpenTelemetry/Collector", "OTel deployment boundary")

    # NODE-66 response headers must still cover trace reset/idempotency short-circuit responses.
    require(app, "_install_final_security_headers", "final security header layer")
    require(app, "HTTP_SECURITY_HEADERS", "NODE-66 header reuse")
    require(app, 'response.headers["Strict-Transport-Security"]', "production HSTS final layer")
    require(boundary_tests, "test_invalid_trace_restarts_without_weakening_node66_security_headers", "trace reset security test")
    require(boundary_tests, "test_production_invalid_trace_restarts_and_keeps_docs_shutdown_hsts", "trace reset production security test")

    # Policy artifacts must be explicitly non-deployed until production proof exists.
    assert dashboard["node"] == "NODE-67"
    assert dashboard["status"] == "SPECIFIED_CORE_NOT_DEPLOYED"
    assert "MUST NOT be metric labels" in dashboard["cardinality_policy"]
    assert len(dashboard["dashboards"]) >= 9
    assert alerts["node"] == "NODE-67"
    assert alerts["status"] == "SPECIFIED_CORE_NOT_ROUTED"
    assert all(rule["owner"] and rule["requires_runbook"] for rule in alerts["rules"])
    assert slo_policy["node"] == "NODE-67"
    assert slo_policy["status"] == "BASELINE_POLICY_NOT_PRODUCTION_VERIFIED"
    assert slo_policy["sampling"]["error_or_critical"] == 1.0

    # Current-track / status / P0 truth.
    require(node_doc, "CORE IMPLEMENTED / VALIDATING / NOT COMPLETE", "canonical NODE status")
    require(current_track, "older PR numbered #67", "legacy PR isolation")
    assert gap_ledger["node"] == "NODE-67"
    assert gap_ledger["status"] == "CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE"
    open_p0 = [
        gap for gap in gap_ledger["gaps"]
        if gap["severity"] == "P0" and gap["status"] == "open"
    ]
    if not open_p0:
        raise SystemExit("NODE67_VALIDATION_FAILED:production P0 gaps must remain open")
    for gap_id in (
        "NODE67-GAP-101",
        "NODE67-GAP-102",
        "NODE67-GAP-103",
        "NODE67-GAP-104",
        "NODE67-GAP-113",
    ):
        if not any(gap["id"] == gap_id and gap["status"] == "open" for gap in gap_ledger["gaps"]):
            raise SystemExit(f"NODE67_VALIDATION_FAILED:required open gap missing:{gap_id}")
    for gap_id in (
        "NODE67-GAP-201",
        "NODE67-GAP-203",
        "NODE67-GAP-205",
        "NODE67-GAP-206",
        "NODE67-GAP-207",
        "NODE67-GAP-209",
        "NODE67-GAP-210",
    ):
        if not any(gap["id"] == gap_id and gap["status"] == "closed" for gap in gap_ledger["gaps"]):
            raise SystemExit(f"NODE67_VALIDATION_FAILED:closed core evidence missing:{gap_id}")

    print("NODE67_OBSERVABILITY_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
