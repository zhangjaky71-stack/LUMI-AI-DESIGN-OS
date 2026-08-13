from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .states import TERMINAL_TASK_STATES, TaskState


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: UUID
    graph_id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_key: str
    recipe_step_id: str
    step_type: str
    owner: str
    status: TaskState
    depends_on: tuple[UUID, ...]
    input_bindings: dict[str, str]
    output_schema: str
    priority: int = 100
    attempt_count: int = 0
    max_attempts: int = 3
    budget_limit_usd: str | None = None
    progress_current: int = 0
    progress_total: int = 1
    dynamic_depth: int = 0
    dynamic_child_limit: int = 0
    concurrency_group: str | None = None
    concurrency_limit: int | None = None
    condition: str | None = None
    wait_reason: str | None = None
    external_ref: str | None = None
    retry_not_before: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    state_version: int = 1
    output: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_key or len(self.task_key) > 255:
            raise ValueError("TASK_KEY_INVALID")
        if self.attempt_count < 0 or not 1 <= self.max_attempts <= 20:
            raise ValueError("TASK_ATTEMPT_LIMIT_INVALID")
        if not 0 <= self.priority <= 1000:
            raise ValueError("TASK_PRIORITY_INVALID")
        if self.progress_total < 1 or not 0 <= self.progress_current <= self.progress_total:
            raise ValueError("TASK_PROGRESS_INVALID")
        if not 0 <= self.dynamic_depth <= 4:
            raise ValueError("TASK_DYNAMIC_DEPTH_INVALID")
        if not 0 <= self.dynamic_child_limit <= 32:
            raise ValueError("TASK_DYNAMIC_CHILD_LIMIT_INVALID")
        if self.concurrency_limit is not None and not 1 <= self.concurrency_limit <= 32:
            raise ValueError("TASK_CONCURRENCY_LIMIT_INVALID")
        if self.state_version < 1:
            raise ValueError("TASK_STATE_VERSION_INVALID")
        if self.budget_limit_usd is not None:
            value = Decimal(self.budget_limit_usd)
            if not value.is_finite() or value <= 0:
                raise ValueError("TASK_BUDGET_INVALID")

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATES

    @property
    def progress(self) -> float:
        return self.progress_current / self.progress_total


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    task_id: UUID
    attempt_number: int
    operation_key: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    error_category: str | None = None
    result_ref: str | None = None
    cost_amount_usd: str | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1 or not self.operation_key:
            raise ValueError("TASK_ATTEMPT_INVALID")
        if self.cost_amount_usd is not None:
            value = Decimal(self.cost_amount_usd)
            if not value.is_finite() or value < 0:
                raise ValueError("TASK_ATTEMPT_COST_INVALID")


def operation_key(graph_id: UUID, task_id: UUID, attempt_number: int) -> str:
    if attempt_number < 1:
        raise ValueError("TASK_ATTEMPT_NUMBER_INVALID")
    return f"task:{graph_id}:{task_id}:attempt:{attempt_number}"
