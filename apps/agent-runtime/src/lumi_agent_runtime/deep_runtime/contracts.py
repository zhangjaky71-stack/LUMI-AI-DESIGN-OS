from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

_AGENT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,255}$")


@dataclass(frozen=True, slots=True)
class DelegationLimits:
    max_depth: int = 2
    max_total_subagent_calls: int = 12
    max_parallel_subagents: int = 3
    max_children_per_agent: int = 6

    def __post_init__(self) -> None:
        if not 0 <= self.max_depth <= 8:
            raise ValueError("DEEP_AGENT_MAX_DEPTH_INVALID")
        if not 0 <= self.max_total_subagent_calls <= 128:
            raise ValueError("DEEP_AGENT_MAX_CALLS_INVALID")
        if not 1 <= self.max_parallel_subagents <= 16:
            raise ValueError("DEEP_AGENT_MAX_PARALLEL_INVALID")
        if not 0 <= self.max_children_per_agent <= 32:
            raise ValueError("DEEP_AGENT_MAX_CHILDREN_INVALID")


@dataclass(frozen=True, slots=True)
class DeepSubagentDefinition:
    name: str
    description: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    model_profile: str
    max_steps: int = 24
    can_delegate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _AGENT_NAME.fullmatch(self.name):
            raise ValueError("DEEP_SUBAGENT_NAME_INVALID")
        if not self.description or len(self.description) > 1000:
            raise ValueError("DEEP_SUBAGENT_DESCRIPTION_INVALID")
        if not self.system_prompt or len(self.system_prompt) > 32000:
            raise ValueError("DEEP_SUBAGENT_PROMPT_INVALID")
        if not _VERSION.fullmatch(self.model_profile):
            raise ValueError("DEEP_SUBAGENT_MODEL_PROFILE_INVALID")
        if not 1 <= self.max_steps <= 128:
            raise ValueError("DEEP_SUBAGENT_MAX_STEPS_INVALID")
        if len(self.allowed_tools) > 128:
            raise ValueError("DEEP_SUBAGENT_TOOL_SCOPE_TOO_LARGE")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("DEEP_SUBAGENT_TOOL_SCOPE_DUPLICATE")
        for tool in self.allowed_tools:
            if not _TOOL_NAME.fullmatch(tool):
                raise ValueError(f"DEEP_SUBAGENT_TOOL_INVALID:{tool}")
        _json_guard(self.metadata, path="$.metadata", depth=0)


@dataclass(frozen=True, slots=True)
class DeepAgentDefinition:
    agent_key: str
    runtime_version: str
    graph_key: str
    graph_version: str
    agent_config_version: str
    system_prompt: str
    model_profile: str
    allowed_tools: tuple[str, ...]
    subagents: tuple[DeepSubagentDefinition, ...]
    delegation: DelegationLimits = field(default_factory=DelegationLimits)
    max_steps: int = 64
    planning_enabled: bool = True
    virtual_files_enabled: bool = True
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _AGENT_NAME.fullmatch(self.agent_key):
            raise ValueError("DEEP_AGENT_KEY_INVALID")
        for value, code in (
            (self.runtime_version, "DEEP_AGENT_RUNTIME_VERSION_INVALID"),
            (self.graph_version, "DEEP_AGENT_GRAPH_VERSION_INVALID"),
            (self.agent_config_version, "DEEP_AGENT_CONFIG_VERSION_INVALID"),
            (self.model_profile, "DEEP_AGENT_MODEL_PROFILE_INVALID"),
        ):
            if not _VERSION.fullmatch(value):
                raise ValueError(code)
        if not self.graph_key or len(self.graph_key) > 128:
            raise ValueError("DEEP_AGENT_GRAPH_KEY_INVALID")
        if not self.system_prompt or len(self.system_prompt) > 64000:
            raise ValueError("DEEP_AGENT_PROMPT_INVALID")
        if not 1 <= self.max_steps <= 256:
            raise ValueError("DEEP_AGENT_MAX_STEPS_INVALID")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("DEEP_AGENT_TOOL_SCOPE_DUPLICATE")
        for tool in self.allowed_tools:
            if not _TOOL_NAME.fullmatch(tool):
                raise ValueError(f"DEEP_AGENT_TOOL_INVALID:{tool}")
        if len(self.subagents) > self.delegation.max_children_per_agent:
            raise ValueError("DEEP_AGENT_CHILD_LIMIT_EXCEEDED")
        names = [item.name for item in self.subagents]
        if len(set(names)) != len(names):
            raise ValueError("DEEP_AGENT_SUBAGENT_DUPLICATE")
        parent_tools = set(self.allowed_tools)
        for child in self.subagents:
            extra = set(child.allowed_tools) - parent_tools
            if extra:
                raise ValueError(
                    f"DEEP_AGENT_SUBAGENT_TOOL_ESCALATION:{child.name}:{','.join(sorted(extra))}"
                )
            if child.can_delegate and self.delegation.max_depth < 2:
                raise ValueError("DEEP_AGENT_DELEGATION_DEPTH_INCONSISTENT")
        _json_guard(self.metadata, path="$.metadata", depth=0)

    @property
    def identity(self) -> str:
        return f"{self.agent_key}@{self.runtime_version}"

    @property
    def content_hash(self) -> str:
        payload = {
            "agent_key": self.agent_key,
            "runtime_version": self.runtime_version,
            "graph_key": self.graph_key,
            "graph_version": self.graph_version,
            "agent_config_version": self.agent_config_version,
            "system_prompt": self.system_prompt,
            "model_profile": self.model_profile,
            "allowed_tools": self.allowed_tools,
            "subagents": [
                {
                    "name": child.name,
                    "description": child.description,
                    "system_prompt": child.system_prompt,
                    "allowed_tools": child.allowed_tools,
                    "model_profile": child.model_profile,
                    "max_steps": child.max_steps,
                    "can_delegate": child.can_delegate,
                    "metadata": child.metadata,
                }
                for child in self.subagents
            ],
            "delegation": {
                "max_depth": self.delegation.max_depth,
                "max_total_subagent_calls": self.delegation.max_total_subagent_calls,
                "max_parallel_subagents": self.delegation.max_parallel_subagents,
                "max_children_per_agent": self.delegation.max_children_per_agent,
            },
            "max_steps": self.max_steps,
            "planning_enabled": self.planning_enabled,
            "virtual_files_enabled": self.virtual_files_enabled,
            "metadata": self.metadata,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class DeepAgentInvocationContext:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    operation_id: UUID
    actor_id: str
    root_agent: str
    granted_permissions: frozenset[str]
    allowed_tools: tuple[str, ...]
    trace_id: str | None = None
    budget_limit_usd: str | None = None

    def __post_init__(self) -> None:
        if not self.actor_id or len(self.actor_id) > 255:
            raise ValueError("DEEP_AGENT_ACTOR_INVALID")
        if not _AGENT_NAME.fullmatch(self.root_agent):
            raise ValueError("DEEP_AGENT_ROOT_INVALID")
        if not self.granted_permissions:
            raise ValueError("DEEP_AGENT_PERMISSIONS_REQUIRED")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("DEEP_AGENT_CONTEXT_TOOL_SCOPE_DUPLICATE")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("DEEP_AGENT_TRACE_ID_INVALID")
        if self.budget_limit_usd is not None and len(self.budget_limit_usd) > 64:
            raise ValueError("DEEP_AGENT_BUDGET_INVALID")


@dataclass(frozen=True, slots=True)
class SubagentInvocationContext:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    operation_id: UUID
    actor_id: str
    root_agent: str
    subagent_name: str
    depth: int
    granted_permissions: frozenset[str]
    parent_allowed_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not _AGENT_NAME.fullmatch(self.subagent_name):
            raise ValueError("DEEP_SUBAGENT_CONTEXT_NAME_INVALID")
        if not 1 <= self.depth <= 8:
            raise ValueError("DEEP_SUBAGENT_CONTEXT_DEPTH_INVALID")
        parent = set(self.parent_allowed_tools)
        child = set(self.allowed_tools)
        if not child <= parent:
            raise ValueError("DEEP_SUBAGENT_CONTEXT_TOOL_ESCALATION")


@dataclass(frozen=True, slots=True)
class DelegationUsage:
    total_calls: int
    active_calls: int
    max_depth_seen: int

    def __post_init__(self) -> None:
        if self.total_calls < 0 or self.active_calls < 0 or self.max_depth_seen < 0:
            raise ValueError("DEEP_AGENT_DELEGATION_USAGE_INVALID")


def _json_guard(value: Any, *, path: str, depth: int) -> None:
    if depth > 20:
        raise ValueError("DEEP_AGENT_METADATA_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"DEEP_AGENT_NONFINITE:{path}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"DEEP_AGENT_NON_STRING_KEY:{path}")
            _json_guard(child, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_guard(child, path=f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"DEEP_AGENT_BINARY_FORBIDDEN:{path}")
    raise ValueError(f"DEEP_AGENT_METADATA_UNSUPPORTED:{path}:{type(value).__name__}")
