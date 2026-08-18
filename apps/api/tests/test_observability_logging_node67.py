from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from lumi_api.observability import (
    LogLevel,
    PythonJsonLoggingSink,
    SafeLangSmithTracer,
    StructuredLogRecord,
)

NOW = datetime(2026, 8, 18, 11, 45, tzinfo=UTC)


class CapturingLangSmithPort:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def emit_agent_trace(self, *, trace_id: str, run_name: str, attributes: dict) -> None:
        self.calls.append(
            {
                "trace_id": trace_id,
                "run_name": run_name,
                "attributes": dict(attributes),
            }
        )


def test_python_logging_sink_emits_parseable_structured_json(caplog) -> None:
    logger_name = "lumi.telemetry.node67.test"
    sink = PythonJsonLoggingSink(logger_name)
    record = StructuredLogRecord(
        level=LogLevel.INFO,
        event="http.request.completed",
        message="HTTP request completed.",
        occurred_at=NOW,
        trace_id="1" * 32,
        span_id="2" * 16,
        request_id="request-1",
        correlation_id="corr-1",
        fields={
            "http.method": "GET",
            "http.route": "/api/v1/projects/{project_id}",
            "http.status_code": 200,
            "duration_ms": 12.5,
        },
    )

    with caplog.at_level(logging.INFO, logger=logger_name):
        sink.emit_log(record)

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].getMessage())
    assert payload["event"] == "http.request.completed"
    assert payload["trace_id"] == "1" * 32
    assert payload["request_id"] == "request-1"
    assert payload["fields"]["http.route"] == "/api/v1/projects/{project_id}"
    assert "prompt" not in payload
    assert "authorization" not in payload


def test_langsmith_fanout_reuses_safe_attribute_boundary() -> None:
    port = CapturingLangSmithPort()
    tracer = SafeLangSmithTracer(port)

    emitted = tracer.emit_agent_trace(
        trace_id="1" * 32,
        run_name="designer-agent",
        attributes={"agent_version": "v1", "capability": "design"},
    )
    assert emitted is True
    assert len(port.calls) == 1
    assert port.calls[0]["attributes"] == {"agent_version": "v1", "capability": "design"}

    leaked = tracer.emit_agent_trace(
        trace_id="1" * 32,
        run_name="designer-agent",
        attributes={"prompt": "private user prompt"},
    )
    assert leaked is False
    assert tracer.dropped == 1
    assert len(port.calls) == 1


def test_langsmith_invalid_run_name_is_dropped_not_raised() -> None:
    port = CapturingLangSmithPort()
    tracer = SafeLangSmithTracer(port)

    emitted = tracer.emit_agent_trace(
        trace_id="1" * 32,
        run_name="raw user prompt must not become a vendor run name",
        attributes={"agent_version": "v1"},
    )
    assert emitted is False
    assert tracer.dropped == 1
    assert port.calls == []
