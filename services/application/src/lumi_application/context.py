from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    organization_id: UUID
    request_id: str
    correlation_id: UUID
    actor_id: UUID | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise ValueError("request_id must contain 1..128 characters")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("trace_id must be <= 128 characters")
