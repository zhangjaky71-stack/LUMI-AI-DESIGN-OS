from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .contracts import LumiRunState, SafeRunEvent


class SafeEventProjector:
    """Projects control-plane lifecycle into UI-safe structured progress.

    It never emits prompts, model messages, scratchpads, tool observations or chain-of-thought.
    """

    def event(
        self,
        event_type: str,
        state: LumiRunState,
        *,
        payload: dict[str, Any] | None = None,
    ) -> SafeRunEvent:
        safe = payload or {}
        forbidden = {
            "prompt",
            "messages",
            "reasoning",
            "chain_of_thought",
            "scratchpad",
            "raw_response",
            "tool_output",
        }
        if forbidden.intersection(safe):
            raise ValueError("GRAPH_EVENT_PRIVATE_REASONING_FORBIDDEN")
        return SafeRunEvent(
            event_type=event_type,
            organization_id=UUID(state["organization_id"]),
            project_id=UUID(state["project_id"]),
            agent_run_id=UUID(state["run_id"]),
            occurred_at=datetime.now(UTC),
            payload=safe,
        )
