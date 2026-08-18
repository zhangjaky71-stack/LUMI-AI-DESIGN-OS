from __future__ import annotations

import re
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator
from uuid import UUID

_TRACEPARENT = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-(?P<span_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)
_TRACESTATE_MEMBER = re.compile(r"^[a-z0-9][_0-9a-z*\-/]{0,255}=[\x20-\x7e]{1,256}$")
_current_context: ContextVar[TelemetryContext | None] = ContextVar(
    "lumi_telemetry_context", default=None
)


def _new_trace_id() -> str:
    value = "0" * 32
    while value == "0" * 32:
        value = secrets.token_hex(16)
    return value


def _new_span_id() -> str:
    value = "0" * 16
    while value == "0" * 16:
        value = secrets.token_hex(8)
    return value


def _validate_tracestate(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 512:
        raise ValueError("OBSERVABILITY_TRACESTATE_TOO_LONG")
    members = [part.strip() for part in normalized.split(",")]
    if len(members) > 32 or any(not member for member in members):
        raise ValueError("OBSERVABILITY_TRACESTATE_INVALID")
    keys: set[str] = set()
    for member in members:
        if not _TRACESTATE_MEMBER.fullmatch(member):
            raise ValueError("OBSERVABILITY_TRACESTATE_INVALID")
        key = member.split("=", 1)[0]
        if key in keys:
            raise ValueError("OBSERVABILITY_TRACESTATE_DUPLICATE_KEY")
        keys.add(key)
    return ",".join(members)


@dataclass(frozen=True, slots=True)
class ParsedTraceParent:
    version: str
    trace_id: str
    parent_span_id: str
    trace_flags: str


def parse_traceparent(value: str | None) -> ParsedTraceParent | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    match = _TRACEPARENT.fullmatch(normalized)
    if match is None:
        raise ValueError("OBSERVABILITY_TRACEPARENT_INVALID")
    version = match.group("version")
    trace_id = match.group("trace_id")
    parent_span_id = match.group("span_id")
    flags = match.group("flags")
    if version == "ff":
        raise ValueError("OBSERVABILITY_TRACEPARENT_VERSION_INVALID")
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        raise ValueError("OBSERVABILITY_TRACEPARENT_ZERO_ID_FORBIDDEN")
    return ParsedTraceParent(
        version=version,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        trace_flags=flags,
    )


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    request_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    trace_flags: str = "01"
    tracestate: str | None = None
    organization_id: UUID | None = None
    project_id: UUID | None = None
    agent_run_id: UUID | None = None
    task_id: UUID | None = None
    operation_id: UUID | None = None
    provider_request_id: UUID | None = None

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    @property
    def sampled(self) -> bool:
        return bool(int(self.trace_flags, 16) & 0x01)

    def with_business_refs(
        self,
        *,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        task_id: UUID | None = None,
        operation_id: UUID | None = None,
        provider_request_id: UUID | None = None,
    ) -> TelemetryContext:
        return replace(
            self,
            organization_id=organization_id or self.organization_id,
            project_id=project_id or self.project_id,
            agent_run_id=agent_run_id or self.agent_run_id,
            task_id=task_id or self.task_id,
            operation_id=operation_id or self.operation_id,
            provider_request_id=provider_request_id or self.provider_request_id,
        )

    def child(self) -> TelemetryContext:
        return replace(self, parent_span_id=self.span_id, span_id=_new_span_id())

    def event_fields(self) -> dict[str, str | None]:
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "traceparent": self.traceparent,
            "tracestate": self.tracestate,
        }


@contextmanager
def start_request_context(
    *,
    request_id: str,
    correlation_id: str | None = None,
    traceparent: str | None = None,
    tracestate: str | None = None,
) -> Iterator[TelemetryContext]:
    incoming = parse_traceparent(traceparent)
    state = _validate_tracestate(tracestate)
    context = TelemetryContext(
        request_id=request_id,
        correlation_id=(correlation_id or request_id).strip(),
        trace_id=incoming.trace_id if incoming else _new_trace_id(),
        span_id=_new_span_id(),
        parent_span_id=incoming.parent_span_id if incoming else None,
        trace_flags=incoming.trace_flags if incoming else "01",
        tracestate=state,
    )
    if not context.correlation_id or len(context.correlation_id) > 128:
        raise ValueError("OBSERVABILITY_CORRELATION_ID_INVALID")
    token = _current_context.set(context)
    try:
        yield context
    finally:
        _current_context.reset(token)


def current_telemetry_context() -> TelemetryContext | None:
    return _current_context.get()
