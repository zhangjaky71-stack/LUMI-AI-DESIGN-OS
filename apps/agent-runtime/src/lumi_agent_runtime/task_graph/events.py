from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ._contract_utils import _aware, _contains_forbidden_event_key, _json_guard


@dataclass(frozen=True, slots=True)
class TaskGraphEvent:
    event_type: str
    graph_id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type or len(self.event_type) > 120:
            raise ValueError("TASK_EVENT_TYPE_INVALID")
        _aware(self.occurred_at, "TASK_EVENT_TIME_INVALID")
        _json_guard(self.payload)
        if _contains_forbidden_event_key(self.payload):
            raise ValueError("TASK_EVENT_PRIVATE_REASONING_FORBIDDEN")
