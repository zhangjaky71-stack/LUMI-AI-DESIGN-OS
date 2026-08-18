from __future__ import annotations

import re
from typing import Any, Protocol

from .models import validate_safe_attributes

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


class LangSmithTracePort(Protocol):
    def emit_agent_trace(
        self,
        *,
        trace_id: str,
        run_name: str,
        attributes: dict[str, Any],
    ) -> None: ...


class SafeLangSmithTracer:
    """Optional Agent/LLM trace fan-out that can never fail the business run.

    The vendor boundary receives only the same bounded safe-attribute shape used by
    the rest of NODE-67 telemetry. Validation failures are treated exactly like
    exporter failures: the optional trace is dropped, never the business run.
    """

    def __init__(self, port: LangSmithTracePort | None = None) -> None:
        self.port = port
        self.dropped = 0

    def emit_agent_trace(
        self,
        *,
        trace_id: str,
        run_name: str,
        attributes: dict[str, Any],
    ) -> bool:
        if self.port is None:
            return False
        try:
            if not _TRACE_ID_RE.fullmatch(trace_id):
                raise ValueError("OBSERVABILITY_LANGSMITH_TRACE_ID_INVALID")
            if not _RUN_NAME_RE.fullmatch(run_name):
                raise ValueError("OBSERVABILITY_LANGSMITH_RUN_NAME_INVALID")
            safe_attributes = validate_safe_attributes(attributes)
            self.port.emit_agent_trace(
                trace_id=trace_id,
                run_name=run_name,
                attributes=safe_attributes,
            )
            return True
        except Exception:
            self.dropped += 1
            return False
