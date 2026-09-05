from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .states import TaskGraphState


@dataclass(frozen=True, slots=True)
class TaskGraphProvenance:
    recipe_id: str
    recipe_version: str
    recipe_definition_hash: str
    recipe_provenance_hash: str
    task_graph_template_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.recipe_definition_hash,
            self.recipe_provenance_hash,
            self.task_graph_template_hash,
        ):
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("TASK_GRAPH_PROVENANCE_HASH_INVALID")

    @property
    def freeze_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class TaskGraphSnapshot:
    graph_id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    provenance: TaskGraphProvenance
    status: TaskGraphState
    recipe_budget_limit_usd: str | None
    task_count: int
    completed_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    skipped_count: int = 0
    cancellation_requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    state_version: int = 1

    def __post_init__(self) -> None:
        if self.task_count < 1 or not 0 <= self.completed_count <= self.task_count:
            raise ValueError("TASK_GRAPH_COUNTER_INVALID")
        if self.state_version < 1:
            raise ValueError("TASK_GRAPH_STATE_VERSION_INVALID")
        if self.recipe_budget_limit_usd is not None:
            value = Decimal(self.recipe_budget_limit_usd)
            if not value.is_finite() or value <= 0:
                raise ValueError("TASK_GRAPH_BUDGET_INVALID")

    @property
    def progress(self) -> float:
        return self.completed_count / self.task_count
