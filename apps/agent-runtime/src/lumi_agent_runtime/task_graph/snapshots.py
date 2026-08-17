from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ._contract_utils import _HASH, _VERSION, _aware, _decimal, _json_guard, _key, _money, _ref
from .definitions import (
    FailureMode,
    JoinPolicy,
    RetryPolicy,
    TaskGraphState,
    TaskKind,
    TaskState,
    TERMINAL_TASK_STATES,
)


@dataclass(frozen=True, slots=True)
class TaskGraphSnapshot:
    graph_id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    graph_key: str
    exact_version: str
    definition_hash: str
    status: TaskGraphState
    budget_limit_usd: str
    cost_spent_usd: str
    max_parallelism: int
    failure_mode: FailureMode
    created_at: datetime
    updated_at: datetime
    state_version: int = 1
    error_code: str | None = None
    pause_requested_at: datetime | None = None
    cancellation_requested_at: datetime | None = None

    def __post_init__(self) -> None:
        _key(self.graph_key, "TASK_GRAPH_KEY_INVALID")
        if not _VERSION.fullmatch(self.exact_version):
            raise ValueError("TASK_GRAPH_VERSION_INVALID")
        if not _HASH.fullmatch(self.definition_hash):
            raise ValueError("TASK_GRAPH_HASH_INVALID")
        limit = _decimal(self.budget_limit_usd, "TASK_GRAPH_BUDGET_INVALID")
        spent = _decimal(self.cost_spent_usd, "TASK_GRAPH_COST_INVALID")
        if limit <= 0 or spent < 0:
            raise ValueError("TASK_GRAPH_BUDGET_INVALID")
        if not 1 <= self.max_parallelism <= 64 or self.state_version < 1:
            raise ValueError("TASK_GRAPH_SNAPSHOT_INVALID")
        _aware(self.created_at, "TASK_GRAPH_CREATED_AT_INVALID")
        _aware(self.updated_at, "TASK_GRAPH_UPDATED_AT_INVALID")

    @property
    def budget_remaining_usd(self) -> str:
        remaining = Decimal(self.budget_limit_usd) - Decimal(self.cost_spent_usd)
        return _money(max(remaining, Decimal("0")))


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: UUID
    graph_id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_key: str
    kind: TaskKind
    objective: str
    status: TaskState
    depends_on: tuple[UUID, ...]
    dependency_keys: tuple[str, ...]
    priority: int
    retry: RetryPolicy
    budget_limit_usd: str | None
    concurrency_group: str | None
    concurrency_limit: int | None
    join_policy: JoinPolicy
    agent_ref: str | None
    context_bundle_ref: str | None
    input_refs: tuple[str, ...]
    metadata: dict[str, Any]
    attempt_count: int = 0
    cost_spent_usd: str = "0"
    lease_owner: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    retry_not_before: datetime | None = None
    cancellation_requested_at: datetime | None = None
    wait_ref: str | None = None
    output_ref: str | None = None
    error_code: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    state_version: int = 1

    def __post_init__(self) -> None:
        _key(self.task_key, "TASK_KEY_INVALID")
        if not self.objective or len(self.objective) > 64_000:
            raise ValueError("TASK_OBJECTIVE_INVALID")
        if self.attempt_count < 0 or self.attempt_count > self.retry.max_attempts:
            raise ValueError("TASK_ATTEMPT_COUNT_INVALID")
        if _decimal(self.cost_spent_usd, "TASK_COST_INVALID") < 0:
            raise ValueError("TASK_COST_INVALID")
        if self.state_version < 1:
            raise ValueError("TASK_STATE_VERSION_INVALID")
        if self.lease_token is not None and self.status is not TaskState.RUNNING:
            raise ValueError("TASK_LEASE_NON_RUNNING")
        if self.lease_owner is None and self.lease_token is not None:
            raise ValueError("TASK_LEASE_OWNER_REQUIRED")
        if self.lease_expires_at is not None:
            _aware(self.lease_expires_at, "TASK_LEASE_EXPIRY_INVALID")
        if self.context_bundle_ref is not None:
            _ref(self.context_bundle_ref, "TASK_CONTEXT_BUNDLE_REF_INVALID")
        if self.output_ref is not None:
            _ref(self.output_ref, "TASK_OUTPUT_REF_INVALID")
        if self.wait_ref is not None:
            _ref(self.wait_ref, "TASK_WAIT_REF_INVALID")
        _json_guard(self.metadata)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATES

    @property
    def logical_operation_key(self) -> str:
        return f"task:{self.graph_id}:{self.task_id}"


@dataclass(frozen=True, slots=True)
class TaskLease:
    task: TaskSnapshot
    worker_id: str
    lease_token: str
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        if not self.worker_id or len(self.worker_id) > 255:
            raise ValueError("TASK_WORKER_ID_INVALID")
        if self.task.status is not TaskState.RUNNING:
            raise ValueError("TASK_LEASE_TASK_NOT_RUNNING")
        if self.task.lease_owner != self.worker_id or self.task.lease_token != self.lease_token:
            raise ValueError("TASK_LEASE_SNAPSHOT_MISMATCH")
        _aware(self.lease_expires_at, "TASK_LEASE_EXPIRY_INVALID")

    @property
    def logical_operation_key(self) -> str:
        return self.task.logical_operation_key


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    task_id: UUID
    attempt_number: int
    worker_id: str
    lease_token: str
    logical_operation_key: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    cost_amount_usd: str = "0"
    error_code: str | None = None
    result_ref: str | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1 or not self.worker_id or not self.lease_token:
            raise ValueError("TASK_ATTEMPT_INVALID")
        if not self.logical_operation_key.startswith("task:"):
            raise ValueError("TASK_LOGICAL_OPERATION_KEY_INVALID")
        _aware(self.started_at, "TASK_ATTEMPT_STARTED_AT_INVALID")
        if self.completed_at is not None:
            _aware(self.completed_at, "TASK_ATTEMPT_COMPLETED_AT_INVALID")
        if _decimal(self.cost_amount_usd, "TASK_ATTEMPT_COST_INVALID") < 0:
            raise ValueError("TASK_ATTEMPT_COST_INVALID")
        if self.result_ref is not None:
            _ref(self.result_ref, "TASK_ATTEMPT_RESULT_REF_INVALID")
