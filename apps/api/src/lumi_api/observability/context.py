from __future__ import annotations

import re
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator
from uuid import UUID

_LOWER_HEX = frozenset("0123456789abcdef")
_TRACESTATE_KEY = re.compile(r"^[a-z0-9][a-z0-9_*/@-]{0,255}$")
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


def _is_lower_hex(value: str) -> bool:
    return bool(value) and all(char in _LOWER_HEX for char in value)


def _validate_tracestate_value(value: str) -> None:
    if not value or len(value) > 256 or value.endswith(" "):
        raise ValueError("OBSERVABILITY_TRACESTATE_INVALID")
    for char in value:
        codepoint = ord(char)
        if codepoint < 0x20 or codepoint > 0x7E or char in {",", "="}:
            raise ValueError("OBSERVABILITY_TRACESTATE_INVALID")


def _validate_tracestate(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 512:
        raise ValueError("OBSERVABILITY_TRACESTATE_TOO_LONG")

    raw_members = normalized.split(",")
    if len(raw_members) > 32:
        raise ValueError("OBSERVABILITY_TRACESTATE_INVALID")

    keys: set[str] = set()
    members: list[str] = []
    for raw_member in raw_members:
        member = raw_member.strip()
        # W3C Trace Context explicitly allows empty/OWS-only list-members.
        if not member:
            continue
        key, separator, member_value = member.partition("=")
        if separator != "=" or not _TRACESTATE_KEY.fullmatch(key):
            raise ValueError("OBSERVABILITY_TRACESTATE_INVALID")
        _validate_tracestate_value(member_value)
        if key in keys:
            raise ValueError("OBSERVABILITY_TRACESTATE_DUPLICATE_KEY")
        keys.add(key)
        members.append(f"{key}={member_value}")

    return ",".join(members) or None


@dataclass(frozen=True, slots=True)
class ParsedTraceParent:
    version: str
    trace_id: str
    parent_span_id: str
    trace_flags: str


def parse_traceparent(value: str | None) -> ParsedTraceParent | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) < 55:
        raise ValueError("OBSERVABILITY_TRACEPARENT_INVALID")
    if normalized[2:3] != "-" or normalized[35:36] != "-" or normalized[52:53] != "-":
        raise ValueError("OBSERVABILITY_TRACEPARENT_INVALID")

    version = normalized[:2]
    trace_id = normalized[3:35]
    parent_span_id = normalized[36:52]
    flags = normalized[53:55]
    if not (
        len(version) == 2
        and _is_lower_hex(version)
        and len(trace_id) == 32
        and _is_lower_hex(trace_id)
        and len(parent_span_id) == 16
        and _is_lower_hex(parent_span_id)
        and len(flags) == 2
        and _is_lower_hex(flags)
    ):
        raise ValueError("OBSERVABILITY_TRACEPARENT_INVALID")
    if version == "ff":
        raise ValueError("OBSERVABILITY_TRACEPARENT_VERSION_INVALID")
    if version == "00" and len(normalized) != 55:
        raise ValueError("OBSERVABILITY_TRACEPARENT_INVALID")
    if version != "00" and len(normalized) > 55 and normalized[55] != "-":
        raise ValueError("OBSERVABILITY_TRACEPARENT_INVALID")
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        raise ValueError("OBSERVABILITY_TRACEPARENT_ZERO_ID_FORBIDDEN")

    # This implementation emits version 00. Preserve the sampled/random bits that
    # are defined by the version we understand and clear unknown future/reserved bits.
    known_flags = f"{int(flags, 16) & 0x03:02x}"
    return ParsedTraceParent(
        version=version,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        trace_flags=known_flags,
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
    # Trace headers are untrusted telemetry metadata. Malformed trace context must
    # never reject the business request: invalid traceparent restarts the trace and
    # invalid tracestate is discarded while a valid traceparent continues.
    try:
        incoming = parse_traceparent(traceparent)
    except ValueError:
        incoming = None

    state: str | None = None
    if incoming is not None:
        try:
            state = _validate_tracestate(tracestate)
        except ValueError:
            state = None

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


@contextmanager
def start_message_context(
    *,
    request_id: str | None,
    correlation_id: str | None,
    traceparent: str | None,
    tracestate: str | None,
    fallback_request_id: str,
) -> Iterator[TelemetryContext]:
    with start_request_context(
        request_id=request_id or fallback_request_id,
        correlation_id=correlation_id,
        traceparent=traceparent,
        tracestate=tracestate,
    ) as context:
        yield context


def bind_business_refs(
    *,
    organization_id: UUID | None = None,
    project_id: UUID | None = None,
    agent_run_id: UUID | None = None,
    task_id: UUID | None = None,
    operation_id: UUID | None = None,
    provider_request_id: UUID | None = None,
) -> TelemetryContext | None:
    current = _current_context.get()
    if current is None:
        return None
    updated = current.with_business_refs(
        organization_id=organization_id,
        project_id=project_id,
        agent_run_id=agent_run_id,
        task_id=task_id,
        operation_id=operation_id,
        provider_request_id=provider_request_id,
    )
    _current_context.set(updated)
    return updated


def current_telemetry_context() -> TelemetryContext | None:
    return _current_context.get()
