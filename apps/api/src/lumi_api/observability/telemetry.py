from __future__ import annotations

import json
import logging
from typing import Protocol

from .models import LogLevel, MetricPoint, SpanRecord, StructuredLogRecord


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


class PythonJsonLoggingSink:
    """Structured JSON log sink using the standard logging pipeline.

    Traces/metrics intentionally remain no-op here; production trace/metric export is
    composed through an OpenTelemetry/Collector adapter rather than pretending the
    Python logger is a metrics backend.
    """

    _LEVELS = {
        LogLevel.DEBUG: logging.DEBUG,
        LogLevel.INFO: logging.INFO,
        LogLevel.WARNING: logging.WARNING,
        LogLevel.ERROR: logging.ERROR,
        LogLevel.CRITICAL: logging.CRITICAL,
    }

    def __init__(self, logger_name: str = "lumi.telemetry") -> None:
        self.logger = logging.getLogger(logger_name)

    def record_span(self, span: SpanRecord) -> None:
        del span

    def record_metric(self, metric: MetricPoint) -> None:
        del metric

    def emit_log(self, record: StructuredLogRecord) -> None:
        payload = record.model_dump(mode="json", exclude_none=True)
        rendered = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        self.logger.log(self._LEVELS[record.level], rendered)


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
