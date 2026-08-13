from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

_GRAPH_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")


class GraphRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InterruptKind(StrEnum):
    APPROVAL = "approval"
    INPUT = "input"
    REVIEW = "review"


class ResumeDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVIDED = "provided"


@dataclass(frozen=True, slots=True)
class GraphDefinition:
    graph_key: str
    graph_version: str
    agent_config_version: str
    description: str
    state_schema_version: int
    input_schema_version: int = 1
    output_schema_version: int = 1
    interrupt_policy_version: str = "1"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _GRAPH_KEY.fullmatch(self.graph_key):
            raise ValueError("GRAPH_KEY_INVALID")
        if not _VERSION.fullmatch(self.graph_version):
            raise ValueError("GRAPH_VERSION_INVALID")
        if not _VERSION.fullmatch(self.agent_config_version):
            raise ValueError("AGENT_CONFIG_VERSION_INVALID")
        if not self.description or len(self.description) > 1000:
            raise ValueError("GRAPH_DESCRIPTION_INVALID")
        if self.state_schema_version < 1 or self.input_schema_version < 1:
            raise ValueError("GRAPH_SCHEMA_VERSION_INVALID")
        if self.output_schema_version < 1:
            raise ValueError("GRAPH_OUTPUT_SCHEMA_VERSION_INVALID")
        if not _VERSION.fullmatch(self.interrupt_policy_version):
            raise ValueError("GRAPH_INTERRUPT_POLICY_VERSION_INVALID")
        _validate_json(self.metadata, path="$.metadata", depth=0)

    @property
    def identity(self) -> str:
        return f"{self.graph_key}@{self.graph_version}"

    @property
    def content_hash(self) -> str:
        payload = {
            "graph_key": self.graph_key,
            "graph_version": self.graph_version,
            "agent_config_version": self.agent_config_version,
            "description": self.description,
            "state_schema_version": self.state_schema_version,
            "input_schema_version": self.input_schema_version,
            "output_schema_version": self.output_schema_version,
            "interrupt_policy_version": self.interrupt_policy_version,
            "metadata": self.metadata,
        }
        encoded = json.dumps(
            _normalize_json(payload, path="$", depth=0),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class GraphRunRequest:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    operation_id: UUID
    graph_key: str
    graph_version: str
    agent_config_version: str
    input: dict[str, Any]
    thread_id: str
    request_id: UUID = field(default_factory=uuid4)
    task_id: UUID | None = None
    budget_limit_usd: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not _GRAPH_KEY.fullmatch(self.graph_key):
            raise ValueError("GRAPH_KEY_INVALID")
        if not _VERSION.fullmatch(self.graph_version):
            raise ValueError("GRAPH_VERSION_INVALID")
        if not _VERSION.fullmatch(self.agent_config_version):
            raise ValueError("AGENT_CONFIG_VERSION_INVALID")
        if not self.thread_id or len(self.thread_id) > 255 or "\x00" in self.thread_id:
            raise ValueError("GRAPH_THREAD_ID_INVALID")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("GRAPH_TRACE_ID_INVALID")
        if self.budget_limit_usd is not None:
            if not self.budget_limit_usd or len(self.budget_limit_usd) > 64:
                raise ValueError("GRAPH_BUDGET_INVALID")
        _validate_json(self.input, path="$.input", depth=0)


@dataclass(frozen=True, slots=True)
class GraphInterrupt:
    interrupt_id: str
    kind: InterruptKind
    namespace: tuple[str, ...]
    node_name: str | None
    payload: dict[str, Any]
    resumable: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.interrupt_id or len(self.interrupt_id) > 512:
            raise ValueError("GRAPH_INTERRUPT_ID_INVALID")
        if len(self.namespace) > 32:
            raise ValueError("GRAPH_INTERRUPT_NAMESPACE_TOO_DEEP")
        for item in self.namespace:
            if not item or len(item) > 255:
                raise ValueError("GRAPH_INTERRUPT_NAMESPACE_INVALID")
        if self.node_name is not None and len(self.node_name) > 255:
            raise ValueError("GRAPH_INTERRUPT_NODE_INVALID")
        _validate_json(self.payload, path="$.interrupt.payload", depth=0)


@dataclass(frozen=True, slots=True)
class GraphRunSnapshot:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    thread_id: str
    graph_key: str
    graph_version: str
    agent_config_version: str
    status: GraphRunStatus
    checkpoint_id: str | None
    checkpoint_namespace: str
    state_values: dict[str, Any]
    next_nodes: tuple[str, ...]
    interrupts: tuple[GraphInterrupt, ...]
    created_at: datetime
    updated_at: datetime
    task_id: UUID | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.checkpoint_id is not None and len(self.checkpoint_id) > 512:
            raise ValueError("GRAPH_CHECKPOINT_ID_INVALID")
        if len(self.checkpoint_namespace) > 1024:
            raise ValueError("GRAPH_CHECKPOINT_NAMESPACE_INVALID")
        _validate_json(self.state_values, path="$.state", depth=0)


@dataclass(frozen=True, slots=True)
class ResumeRequest:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    operation_id: UUID
    thread_id: str
    interrupt_id: str
    decision: ResumeDecision
    value: Any
    request_id: UUID = field(default_factory=uuid4)
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.thread_id or len(self.thread_id) > 255:
            raise ValueError("GRAPH_THREAD_ID_INVALID")
        if not self.interrupt_id or len(self.interrupt_id) > 512:
            raise ValueError("GRAPH_INTERRUPT_ID_INVALID")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("GRAPH_TRACE_ID_INVALID")
        _validate_json(self.value, path="$.resume.value", depth=0)


@dataclass(frozen=True, slots=True)
class ResumeAuthorization:
    approval_id: UUID | None
    approved: bool
    bound_interrupt_id: str
    normalized_value: Any
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.bound_interrupt_id or len(self.bound_interrupt_id) > 512:
            raise ValueError("GRAPH_RESUME_BINDING_INVALID")
        if self.reason is not None and len(self.reason) > 2000:
            raise ValueError("GRAPH_RESUME_REASON_INVALID")
        _validate_json(self.normalized_value, path="$.authorization.value", depth=0)


@dataclass(frozen=True, slots=True)
class CheckpointPointer:
    thread_id: str
    checkpoint_namespace: str
    checkpoint_id: str | None


@dataclass(frozen=True, slots=True)
class GraphRunEvent:
    event_type: str
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    thread_id: str
    graph_key: str
    graph_version: str
    checkpoint_id: str | None
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_type or len(self.event_type) > 128:
            raise ValueError("GRAPH_EVENT_TYPE_INVALID")
        _validate_json(self.payload, path="$.event.payload", depth=0)


def _validate_json(value: Any, *, path: str, depth: int) -> None:
    _normalize_json(value, path=path, depth=depth)


def _normalize_json(value: Any, *, path: str, depth: int) -> Any:
    if depth > 24:
        raise ValueError("GRAPH_JSON_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"GRAPH_NON_FINITE_NUMBER:{path}")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"GRAPH_JSON_NON_STRING_KEY:{path}")
            normalized[key] = _normalize_json(
                child,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json(child, path=f"{path}[{index}]", depth=depth + 1)
            for index, child in enumerate(value)
        ]
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"GRAPH_BINARY_VALUE_FORBIDDEN:{path}")
    raise ValueError(f"GRAPH_JSON_VALUE_UNSUPPORTED:{path}:{type(value).__name__}")
