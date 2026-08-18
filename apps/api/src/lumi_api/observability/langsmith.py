from __future__ import annotations

from typing import Any, Protocol


class LangSmithTracePort(Protocol):
    def emit_agent_trace(
        self,
        *,
        trace_id: str,
        run_name: str,
        attributes: dict[str, Any],
    ) -> None: ...


class SafeLangSmithTracer:
    """Optional Agent/LLM trace fan-out that can never fail the business run."""

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
            self.port.emit_agent_trace(
                trace_id=trace_id,
                run_name=run_name,
                attributes=attributes,
            )
            return True
        except Exception:
            self.dropped += 1
            return False
