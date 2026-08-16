from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, TypedDict
from uuid import UUID, uuid4

_GRAPH_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_MAX_STATE_BYTES = 1_048_576
_EVENT_FORBIDDEN_KEYS = {
    "prompt",
    "messages",
    "reasoning",
    "chain_of_thought",
    "scratchpad",
    "raw_response",
    "tool_output",
}


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_EXTERNAL = "waiting_external"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class NodeCategory(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENTIC = "agentic"
    SIDE_EFFECT = "side_effect"
    WAIT_EXTERNAL = "wait_external"
    HUMAN_INTERRUPT = "human_interrupt"


class ResumeKind(StrEnum):
    APPROVAL = "approval"
    EXTERNAL_JOB = "external_job"
    INPUT = "input"


class LumiRunState(TypedDict, total=False):
    run_id: str
    organization_id: str
    project_id: str
    task_id: str | None
    brief_version: int
    recipe_version: str | None
    current_task_ids: list[str]
    approval_id: str | None
    status: str
    context_refs: list[str]
    artifact_refs: list[str]
    budget_remaining: str
    errors: list[dict[str, Any]]
    graph_key: str
    graph_version: str
    code_git_sha: str
    route: str
    external_job_id: str | None
    repair_iteration: int
    max_repair_iterations: int


_STATE_KEYS = frozenset(LumiRunState.__annotations__)


@dataclass(frozen=True, slots=True)
class GraphDefinition:
    graph_key: str
    graph_version: str
    code_git_sha: str
    state_schema_version: int = 1
    agent_config_version: str = "1"
    description: str = "LUMI main LangGraph control plane"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _GRAPH_KEY.fullmatch(self.graph_key):
            raise ValueError("GRAPH_KEY_INVALID")
        if not _VERSION.fullmatch(self.graph_version):
            raise ValueError("GRAPH_VERSION_INVALID")
        if not _VERSION.fullmatch(self.agent_config_version):
            raise ValueError("AGENT_CONFIG_VERSION_INVALID")
        if not self.code_git_sha or len(self.code_git_sha) > 80:
            raise ValueError("GRAPH_CODE_SHA_INVALID")
        if self.state_schema_version < 1:
            raise ValueError("GRAPH_STATE_SCHEMA_VERSION_INVALID")
        _validate_json(self.metadata, "$.metadata")

    @property
    def identity(self) -> str:
        return f"{self.graph_key}@{self.graph_version}"

    @property
    def content_hash(self) -> str:
        payload = asdict(self)
        encoded = json.dumps(
            _jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class StartRunCommand:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    operation_id: UUID
    brief_version: int
    budget_remaining: str
    graph_key: str = "lumi.main"
    graph_version: str = "1.0.0"
    agent_config_version: str = "1"
    code_git_sha: str = "unknown"
    task_id: UUID | None = None
    thread_id: str | None = None
    trace_id: str | None = None
    request_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.brief_version < 1:
            raise ValueError("GRAPH_BRIEF_VERSION_INVALID")
        if not _GRAPH_KEY.fullmatch(self.graph_key):
            raise ValueError("GRAPH_KEY_INVALID")
        if not _VERSION.fullmatch(self.graph_version):
            raise ValueError("GRAPH_VERSION_INVALID")
        if self.thread_id is not None and (not self.thread_id or len(self.thread_id) > 255):
            raise ValueError("GRAPH_THREAD_ID_INVALID")
        _validate_budget(self.budget_remaining)

    @property
    def effective_thread_id(self) -> str:
        return self.thread_id or str(self.agent_run_id)

    def initial_state(self) -> LumiRunState:
        state: LumiRunState = {
            "run_id": str(self.agent_run_id),
            "organization_id": str(self.organization_id),
            "project_id": str(self.project_id),
            "task_id": str(self.task_id) if self.task_id else None,
            "brief_version": self.brief_version,
            "recipe_version": None,
            "current_task_ids": [],
            "approval_id": None,
            "status": RunStatus.PENDING.value,
            "context_refs": [],
            "artifact_refs": [],
            "budget_remaining": self.budget_remaining,
            "errors": [],
            "graph_key": self.graph_key,
            "graph_version": self.graph_version,
            "code_git_sha": self.code_git_sha,
            "route": "",
            "external_job_id": None,
            "repair_iteration": 0,
            "max_repair_iterations": 2,
        }
        validate_run_state(state)
        return state


@dataclass(frozen=True, slots=True)
class ResumeRunCommand:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    operation_id: UUID
    thread_id: str
    resume_version: int
    interrupt_id: str
    kind: ResumeKind
    value: Any
    expected_graph_key: str
    expected_graph_version: str
    expected_code_git_sha: str
    trace_id: str | None = None
    request_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.thread_id or len(self.thread_id) > 255:
            raise ValueError("GRAPH_THREAD_ID_INVALID")
        if self.resume_version < 1:
            raise ValueError("GRAPH_RESUME_VERSION_INVALID")
        if not self.interrupt_id or len(self.interrupt_id) > 512:
            raise ValueError("GRAPH_INTERRUPT_ID_INVALID")
        _validate_json(self.value, "$.resume")


@dataclass(frozen=True, slots=True)
class RunControlSnapshot:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    thread_id: str
    graph_key: str
    graph_version: str
    code_git_sha: str
    status: RunStatus
    checkpoint_id: str | None
    checkpoint_namespace: str
    state: LumiRunState
    next_nodes: tuple[str, ...]
    interrupts: tuple[dict[str, Any], ...]
    resume_version: int
    created_at: datetime
    updated_at: datetime
    task_id: UUID | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        validate_run_state(self.state)
        _validate_json(list(self.interrupts), "$.interrupts")
        if self.resume_version < 1:
            raise ValueError("GRAPH_RESUME_VERSION_INVALID")


@dataclass(frozen=True, slots=True)
class SafeRunEvent:
    event_type: str
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in {
            "run.started",
            "node.started",
            "agent.status",
            "agent.delta",
            "tool.call",
            "task.progress",
            "approval.required",
            "artifact.created",
            "run.completed",
            "run.cancelled",
            "run.waiting_external",
        }:
            raise ValueError("GRAPH_EVENT_TYPE_INVALID")
        _validate_json(self.payload, "$.event")
        if _contains_forbidden_key(self.payload):
            raise ValueError("GRAPH_EVENT_PRIVATE_REASONING_FORBIDDEN")


def validate_run_state(state: LumiRunState) -> None:
    unknown = set(state) - _STATE_KEYS
    if unknown:
        raise ValueError(f"GRAPH_STATE_UNKNOWN_KEYS:{','.join(sorted(unknown))}")
    if "budget_remaining" in state:
        _validate_budget(state["budget_remaining"])
    normalized = _jsonable(dict(state))
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) > _MAX_STATE_BYTES:
        raise ValueError("GRAPH_STATE_TOO_LARGE")
    for value in _walk_values(normalized):
        if isinstance(value, str) and value.startswith("data:"):
            raise ValueError("GRAPH_STATE_INLINE_DATA_URI_FORBIDDEN")


def _validate_json(value: Any, path: str) -> None:
    try:
        _jsonable(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GRAPH_JSON_INVALID:{path}") from exc


def _validate_budget(value: str) -> None:
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("GRAPH_BUDGET_INVALID") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("GRAPH_BUDGET_INVALID")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("GRAPH_NON_FINITE_NUMBER")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("GRAPH_JSON_NON_STRING_KEY")
            result[key] = _jsonable(child)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("GRAPH_BINARY_VALUE_FORBIDDEN")
    raise TypeError(f"GRAPH_JSON_VALUE_UNSUPPORTED:{type(value).__name__}")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in _EVENT_FORBIDDEN_KEYS or _contains_forbidden_key(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def _walk_values(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value
