from __future__ import annotations

from typing import Protocol

from .models import MetricPoint, SpanRecord, StructuredLogRecord


class TelemetrySink(Protocol):
    def record_span(self, span: SpanRecord) -> None: ...

    def record_metric(self, metric: MetricPoint) -> None: ...

    def emit_log(self, record: StructuredLogRecord) -> None: ...


class NoopTelemetrySink:
    def record_span(self, span: SpanRecord) -> None:
        del span

    def record_metric(self, metric: MetricPoint) -> None:
        del metric

    def emit_log(self, record: StructuredLogRecord) -> None:
        del record


class SafeTelemetry:
    """Fail-open telemetry wrapper.

    Observability must never become a business availability dependency. Exporter,
    Collector, or LangSmith failures are counted by the production adapter but are
    swallowed at this boundary so request/run semantics remain authoritative.
    """

    def __init__(self, sink: TelemetrySink | None = None) -> None:
        self.sink = sink or NoopTelemetrySink()
        self.dropped_spans = 0
        self.dropped_metrics = 0
        self.dropped_logs = 0

    def record_span(self, span: SpanRecord) -> None:
        try:
            self.sink.record_span(span)
        except Exception:
            self.dropped_spans += 1

    def record_metric(self, metric: MetricPoint) -> None:
        try:
            self.sink.record_metric(metric)
        except Exception:
            self.dropped_metrics += 1

    def emit_log(self, record: StructuredLogRecord) -> None:
        try:
            self.sink.emit_log(record)
        except Exception:
            self.dropped_logs += 1
