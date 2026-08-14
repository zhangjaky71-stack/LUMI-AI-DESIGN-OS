from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TaskGraphEvent:
    event_name: str
    graph_id: UUID
    task_id: UUID | None
    organization_id: UUID
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_name.startswith("task"):
            raise ValueError("TASK_GRAPH_EVENT_NAME_INVALID")
