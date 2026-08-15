from __future__ import annotations

import importlib
import json
import re
import secrets
import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import time
from typing import Any, Mapping

from lumi_api.security import redact_secrets


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TRACEPARENT_RE = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$",
    re.IGNORECASE,
)
_FORBIDDEN_LOG_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "prompt",
        "request_body",
        "response_body",
        "signed_url",
        "token",
        "user_content",
    }
)
_ALLOWED_METRIC_LABELS = frozenset(
    {"method", "outcome", "provider", "reason", "route", "service", "status_class"}
)
_DEFAULT_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    service_name: str
    environment: str
    metrics_path: str = "/internal/metrics"
    metrics_enabled: bool = True


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    request_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    organization_id: str | None = None
    project_id: str | None = None
    agent_run_id: str | None = None
    task_id: str | None = None
    operation_id: str | None = None
    provider_request_id: str | None = None

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-01"

    def safe_refs(self) -> dict[str, str]:
        refs = {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
        }
        for name in (
            "organization_id",
            "project_id",
            "agent_run_id",
            "task_id",
            "operation_id",
            "provider_request_id",
        ):
            value = getattr(self, name)
            if value:
                refs[name] = value
        return refs


_current_correlation: ContextVar[CorrelationContext | None] = ContextVar(
    "lumi_correlation_context",
    default=None,
)


def current_correlation() -> CorrelationContext | None:
    return _current_correlation.get()


def bind_correlation(context: CorrelationContext) -> Token[CorrelationContext | None]:
    return _current_correlation.set(context)


def reset_correlation(token: Token[CorrelationContext | None]) -> None:
    _current_correlation.reset(token)


def safe_external_id(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not _ID_RE.fullmatch(candidate):
        return None
    return candidate


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    match = _TRACEPARENT_RE.fullmatch(value.strip())
    if not match:
        return None
    trace_id, parent_span_id, _flags = match.groups()
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        return None
    return trace_id.lower(), parent_span_id.lower()


def active_otel_trace_id() -> str | None:
    """Return the active OpenTelemetry trace id when the API package is installed.

    OpenTelemetry remains optional at import time so frozen installs stay reproducible.
    Production images must install/configure the SDK before NODE-67 can be signed off.
    """

    try:
        trace_module = importlib.import_module("opentelemetry.trace")
        span = trace_module.get_current_span()
        span_context = span.get_span_context()
        if not span_context.is_valid:
            return None
        return f"{span_context.trace_id:032x}"
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def new_correlation_context(
    *,
    request_id: str | None,
    correlation_id: str | None,
    traceparent: str | None,
) -> CorrelationContext:
    incoming = parse_traceparent(traceparent)
    trace_id = active_otel_trace_id() or (incoming[0] if incoming else secrets.token_hex(16))
    safe_request = safe_external_id(request_id) or secrets.token_hex(16)
    safe_correlation = safe_external_id(correlation_id) or safe_request
    return CorrelationContext(
        request_id=safe_request,
        correlation_id=safe_correlation,
        trace_id=trace_id,
        span_id=secrets.token_hex(8),
    )


def safe_log_record(
    *,
    level: str,
    service: str,
    environment: str,
    event: str,
    fields: Mapping[str, Any] | None = None,
    context: CorrelationContext | None = None,
) -> dict[str, Any]:
    if not event or len(event) > 160:
        raise ValueError("OBSERVABILITY_EVENT_INVALID")
    safe_fields: dict[str, Any] = {}
    for raw_key, raw_value in (fields or {}).items():
        key = str(raw_key).strip().lower()
        if key in _FORBIDDEN_LOG_KEYS:
            continue
        if not key or len(key) > 80:
            continue
        safe_fields[key] = _safe_scalar(raw_value)

    payload: dict[str, Any] = {
        "timestamp": time(),
        "level": level.upper(),
        "service": service,
        "environment": environment,
        "event": event,
    }
    active = context or current_correlation()
    if active is not None:
        payload.update(active.safe_refs())
    payload.update(safe_fields)
    return payload


def encode_log(record: Mapping[str, Any]) -> str:
    return redact_secrets(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_secrets(value[:512])
    return redact_secrets(str(value)[:512])


class BoundedMetrics:
    """Small in-process metric surface with an intentionally bounded label vocabulary.

    This is the application-facing compatibility layer for NODE-67. The Collector is
    the vendor boundary. Tenant/user/project/run IDs are deliberately forbidden as
    metric labels and remain trace/log references instead.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[int, float, list[int]],
        ] = {}

    def increment(
        self,
        name: str,
        *,
        value: float = 1.0,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        key = (self._metric_name(name), self._labels(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        key = (self._metric_name(name), self._labels(labels))
        with self._lock:
            count, total, buckets = self._histograms.get(
                key,
                (0, 0.0, [0] * len(_DEFAULT_BUCKETS)),
            )
            for index, upper in enumerate(_DEFAULT_BUCKETS):
                if value <= upper:
                    buckets[index] += 1
            self._histograms[key] = (count + 1, total + value, buckets)

    def observe_http(self, *, method: str, route: str, status_code: int, duration: float) -> None:
        labels = {
            "method": method.upper()[:16],
            "route": _bounded_route(route),
            "status_class": f"{status_code // 100}xx",
        }
        self.increment("lumi_http_requests_total", labels=labels)
        self.observe("lumi_http_request_duration_seconds", duration, labels=labels)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = list(self._counters.items())
            histograms = list(self._histograms.items())
        for (name, labels), value in sorted(counters):
            lines.append(f"{name}{_format_labels(labels)} {value:g}")
        for (name, labels), (count, total, buckets) in sorted(histograms):
            for upper, bucket_count in zip(_DEFAULT_BUCKETS, buckets, strict=True):
                bucket_labels = tuple(labels) + (("le", f"{upper:g}"),)
                lines.append(f"{name}_bucket{_format_labels(bucket_labels)} {bucket_count}")
            inf_labels = tuple(labels) + (("le", "+Inf"),)
            lines.append(f"{name}_bucket{_format_labels(inf_labels)} {count}")
            lines.append(f"{name}_count{_format_labels(labels)} {count}")
            lines.append(f"{name}_sum{_format_labels(labels)} {total:g}")
        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _metric_name(value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z_:][a-zA-Z0-9_:]{0,127}", value):
            raise ValueError("OBSERVABILITY_METRIC_NAME_INVALID")
        return value

    @staticmethod
    def _labels(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
        normalized: list[tuple[str, str]] = []
        for key, value in sorted((labels or {}).items()):
            if key not in _ALLOWED_METRIC_LABELS:
                raise ValueError(f"OBSERVABILITY_HIGH_CARDINALITY_LABEL_FORBIDDEN:{key}")
            normalized.append((key, str(value)[:120]))
        return tuple(normalized)


def _bounded_route(route: str) -> str:
    cleaned = route.strip()
    if not cleaned or len(cleaned) > 200:
        return "unmatched"
    return cleaned


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    encoded = ",".join(
        f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for key, value in labels
    )
    return "{" + encoded + "}"
