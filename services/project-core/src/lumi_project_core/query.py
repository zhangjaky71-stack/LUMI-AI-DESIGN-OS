from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .lifecycle import ProjectStatus


@dataclass(frozen=True, slots=True)
class ProjectListFilter:
    status: ProjectStatus | None = None
    workspace_id: str | None = None
    created_by: str | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    name_query: str | None = None

    def __post_init__(self) -> None:
        if self.status is not None and self.status not in {"draft", "active", "paused", "archived"}:
            raise ValueError("status is invalid")
        if self.updated_after and self.updated_before and self.updated_after > self.updated_before:
            raise ValueError("updated_after must not be after updated_before")
        if self.name_query is not None:
            value = self.name_query.strip()
            if not value or len(value) > 200:
                raise ValueError("name_query is invalid")
