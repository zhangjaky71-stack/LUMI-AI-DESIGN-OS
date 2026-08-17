from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid5

from ._contract_utils import (
    _AGENT_REF,
    _assert_acyclic,
    _decimal,
    _json_guard,
    _jsonable,
    _key,
    _ref,
    _sha256,
    _unique,
    _VERSION,
)


class TaskKind(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENTIC = "agentic"
    SIDE_EFFECT = "side_effect"
    WAIT_EXTERNAL = "wait_external"
    APPROVAL = "approval"


class TaskState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_EXTERNAL = "waiting_external"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TaskGraphState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    FAILURE_DRAINING = "failure_draining"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED_FINAL = "failed_final"
    CANCELLED = "cancelled"


class FailureMode(StrEnum):
    FAIL_FAST = "fail_fast"
    CONTINUE = "continue"


class JoinPolicy(StrEnum):
    ALL_SUCCESS = "all_success"
    ALL_TERMINAL = "all_terminal"
    ANY_SUCCESS = "any_success"

TERMINAL_TASK_STATES = frozenset(
    {TaskState.SUCCEEDED, TaskState.FAILED_FINAL, TaskState.CANCELLED, TaskState.SKIPPED}
)
WAITING_TASK_STATES = frozenset({TaskState.WAITING_USER, TaskState.WAITING_EXTERNAL})
TERMINAL_GRAPH_STATES = frozenset(
    {TaskGraphState.SUCCEEDED, TaskGraphState.FAILED_FINAL, TaskGraphState.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: int = 5
    max_delay_seconds: int = 300
    backoff_multiplier: str = "2"

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 20:
            raise ValueError("TASK_RETRY_MAX_ATTEMPTS_INVALID")
        if not 0 <= self.base_delay_seconds <= 86_400:
            raise ValueError("TASK_RETRY_BASE_DELAY_INVALID")
        if not self.base_delay_seconds <= self.max_delay_seconds <= 604_800:
            raise ValueError("TASK_RETRY_MAX_DELAY_INVALID")
        multiplier = _decimal(self.backoff_multiplier, "TASK_RETRY_MULTIPLIER_INVALID")
        if multiplier < Decimal("1") or multiplier > Decimal("16"):
            raise ValueError("TASK_RETRY_MULTIPLIER_INVALID")

    def delay_seconds(self, attempt_number: int) -> int:
        if attempt_number < 1:
            raise ValueError("TASK_RETRY_ATTEMPT_INVALID")
        multiplier = Decimal(self.backoff_multiplier)
        delay = Decimal(self.base_delay_seconds) * (multiplier ** (attempt_number - 1))
        return min(self.max_delay_seconds, int(delay))


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    task_key: str
    kind: TaskKind
    objective: str
    depends_on: tuple[str, ...] = ()
    priority: int = 100
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    budget_limit_usd: str | None = None
    concurrency_group: str | None = None
    concurrency_limit: int | None = None
    join_policy: JoinPolicy = JoinPolicy.ALL_SUCCESS
    agent_ref: str | None = None
    context_bundle_ref: str | None = None
    input_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _key(self.task_key, "TASK_KEY_INVALID")
        if not self.objective or len(self.objective) > 64_000:
            raise ValueError("TASK_OBJECTIVE_INVALID")
        _unique(self.depends_on, "TASK_DEPENDENCY_DUPLICATE")
        for dep in self.depends_on:
            _key(dep, "TASK_DEPENDENCY_KEY_INVALID")
        if self.task_key in self.depends_on:
            raise ValueError("TASK_SELF_DEPENDENCY")
        if not 0 <= self.priority <= 1000:
            raise ValueError("TASK_PRIORITY_INVALID")
        if self.budget_limit_usd is not None:
            if _decimal(self.budget_limit_usd, "TASK_BUDGET_INVALID") <= 0:
                raise ValueError("TASK_BUDGET_INVALID")
        if self.concurrency_group is not None:
            _key(self.concurrency_group, "TASK_CONCURRENCY_GROUP_INVALID")
            if self.concurrency_limit is None:
                raise ValueError("TASK_CONCURRENCY_LIMIT_REQUIRED")
        if self.concurrency_limit is not None:
            if self.concurrency_group is None or not 1 <= self.concurrency_limit <= 64:
                raise ValueError("TASK_CONCURRENCY_LIMIT_INVALID")
        if self.kind is TaskKind.AGENTIC:
            if self.agent_ref is None or not _AGENT_REF.fullmatch(self.agent_ref):
                raise ValueError("TASK_AGENT_EXACT_REF_REQUIRED")
            if self.context_bundle_ref is None or not self.context_bundle_ref.startswith(
                "context-bundle://"
            ):
                raise ValueError("TASK_CONTEXT_BUNDLE_REF_REQUIRED")
        elif self.agent_ref is not None:
            raise ValueError("TASK_AGENT_REF_ONLY_AGENTIC")
        if self.context_bundle_ref is not None:
            _ref(self.context_bundle_ref, "TASK_CONTEXT_BUNDLE_REF_INVALID")
        _unique(self.input_refs, "TASK_INPUT_REF_DUPLICATE")
        for value in self.input_refs:
            _ref(value, "TASK_INPUT_REF_INVALID")
        _json_guard(self.metadata)


@dataclass(frozen=True, slots=True)
class TaskGraphDefinition:
    graph_key: str
    exact_version: str
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    tasks: tuple[TaskDefinition, ...]
    budget_limit_usd: str
    max_parallelism: int = 4
    failure_mode: FailureMode = FailureMode.FAIL_FAST
    provenance_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _key(self.graph_key, "TASK_GRAPH_KEY_INVALID")
        if not _VERSION.fullmatch(self.exact_version):
            raise ValueError("TASK_GRAPH_VERSION_INVALID")
        if not 1 <= len(self.tasks) <= 2048:
            raise ValueError("TASK_GRAPH_TASK_COUNT_INVALID")
        if not 1 <= self.max_parallelism <= 64:
            raise ValueError("TASK_GRAPH_MAX_PARALLELISM_INVALID")
        budget = _decimal(self.budget_limit_usd, "TASK_GRAPH_BUDGET_INVALID")
        if budget <= 0:
            raise ValueError("TASK_GRAPH_BUDGET_INVALID")
        _unique(tuple(task.task_key for task in self.tasks), "TASK_GRAPH_TASK_KEY_DUPLICATE")
        by_key = {task.task_key: task for task in self.tasks}
        group_limits: dict[str, int] = {}
        for task in self.tasks:
            if task.budget_limit_usd is not None and Decimal(task.budget_limit_usd) > budget:
                raise ValueError("TASK_BUDGET_EXCEEDS_GRAPH_BUDGET")
            for dependency in task.depends_on:
                if dependency not in by_key:
                    raise ValueError(f"TASK_GRAPH_DEPENDENCY_MISSING:{dependency}")
            if task.concurrency_group is not None:
                limit = int(task.concurrency_limit or 0)
                prior = group_limits.setdefault(task.concurrency_group, limit)
                if prior != limit:
                    raise ValueError("TASK_CONCURRENCY_GROUP_LIMIT_CONFLICT")
        _assert_acyclic(self.tasks)
        _unique(self.provenance_refs, "TASK_GRAPH_PROVENANCE_DUPLICATE")
        for value in self.provenance_refs:
            _ref(value, "TASK_GRAPH_PROVENANCE_REF_INVALID")
        _json_guard(self.metadata)

    @property
    def definition_hash(self) -> str:
        payload = {
            "graph_key": self.graph_key,
            "exact_version": self.exact_version,
            "organization_id": str(self.organization_id),
            "project_id": str(self.project_id),
            "agent_run_id": str(self.agent_run_id),
            "tasks": [_jsonable(asdict(task)) for task in self.tasks],
            "budget_limit_usd": self.budget_limit_usd,
            "max_parallelism": self.max_parallelism,
            "failure_mode": self.failure_mode.value,
            "provenance_refs": list(self.provenance_refs),
            "metadata": _jsonable(self.metadata),
        }
        return _sha256(payload)

    @property
    def graph_id(self) -> UUID:
        return uuid5(
            self.agent_run_id,
            f"{self.organization_id}:{self.project_id}:{self.definition_hash}",
        )

    def task_id(self, task_key: str) -> UUID:
        return uuid5(self.graph_id, task_key)
