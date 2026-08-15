from __future__ import annotations

import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Mapping

_TRACE_ID = re.compile(r"^[0-9a-fA-F]{32}$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class WorkerCorrelationContext:
    event_id: str
    correlation_id: str
    trace_id: str | None
    organization_id: str
    causation_id: str | None = None

    def safe_refs(self) -> dict[str, str]:
        refs = {
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
        }
        if self.trace_id:
            refs["trace_id"] = self.trace_id
        if self.causation_id:
            refs["causation_id"] = self.causation_id
        return refs


_current_worker_correlation: ContextVar[WorkerCorrelationContext | None] = ContextVar(
    "lumi_worker_correlation",
    default=None,
)


def current_worker_correlation() -> WorkerCorrelationContext | None:
    return _current_worker_correlation.get()


def bind_event_correlation(
    envelope: Mapping[str, Any],
) -> Token[WorkerCorrelationContext | None]:
    context = WorkerCorrelationContext(
        event_id=_required_ref(envelope.get("id"), "event_id"),
        correlation_id=_required_ref(envelope.get("correlationid"), "correlation_id"),
        trace_id=_trace_id(envelope.get("traceid")),
        organization_id=_required_ref(
            envelope.get("organizationid"),
            "organization_id",
        ),
        causation_id=_optional_ref(envelope.get("causationid")),
    )
    return _current_worker_correlation.set(context)


def reset_event_correlation(token: Token[WorkerCorrelationContext | None]) -> None:
    _current_worker_correlation.reset(token)


def event_telemetry_projection(envelope: Mapping[str, Any]) -> dict[str, str]:
    """Return bounded telemetry refs; event payload/data is intentionally excluded."""

    event_type = str(envelope.get("type") or "unknown")[:120]
    outcome = str(envelope.get("telemetry_outcome") or "received")[:32]
    return {
        "event_type": event_type,
        "outcome": outcome,
    }


def _trace_id(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate.lower() if _TRACE_ID.fullmatch(candidate) else None


def _required_ref(value: Any, name: str) -> str:
    candidate = _optional_ref(value)
    if candidate is None:
        raise ValueError(f"WORKER_OBSERVABILITY_{name.upper()}_INVALID")
    return candidate


def _optional_ref(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate if _SAFE_REF.fullmatch(candidate) else None
