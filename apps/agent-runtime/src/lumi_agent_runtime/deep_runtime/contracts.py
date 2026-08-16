from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID

_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_.-]{0,255}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_MEMORY_SCOPE = re.compile(r"^(project|brand|user|organization)(:[A-Za-z0-9_.-]+)?$")
_MAX_TEXT = 64_000


class AgentTaskStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DelegationLimits:
    max_depth: int = 1
    max_total_subagent_calls: int = 12
    max_parallel_subagents: int = 3
    max_children_per_agent: int = 6

    def __post_init__(self) -> None:
        if not 0 <= self.max_depth <= 4:
            raise ValueError("DEEP_AGENT_MAX_DEPTH_INVALID")
        if not 0 <= self.max_total_subagent_calls <= 128:
            raise ValueError("DEEP_AGENT_MAX_CALLS_INVALID")
        if not 1 <= self.max_parallel_subagents <= 16:
            raise ValueError("DEEP_AGENT_MAX_PARALLEL_INVALID")
        if not 0 <= self.max_children_per_agent <= 32:
            raise ValueError("DEEP_AGENT_MAX_CHILDREN_INVALID")


@dataclass(frozen=True, slots=True)
class PermissionScope:
    allowed_tools: tuple[str, ...]
    sandbox_execute: bool = False
    memory_read_scopes: tuple[str, ...] = ()
    memory_write_scopes: tuple[str, ...] = ()
    allowed_subagents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _unique(self.allowed_tools, "DEEP_PERMISSION_TOOL_DUPLICATE")
        _unique(self.memory_read_scopes, "DEEP_PERMISSION_MEMORY_READ_DUPLICATE")
        _unique(self.memory_write_scopes, "DEEP_PERMISSION_MEMORY_WRITE_DUPLICATE")
        _unique(self.allowed_subagents, "DEEP_PERMISSION_SUBAGENT_DUPLICATE")
        for tool in self.allowed_tools:
            if not _TOOL.fullmatch(tool):
                raise ValueError(f"DEEP_PERMISSION_TOOL_INVALID:{tool}")
        for scope in self.memory_read_scopes + self.memory_write_scopes:
            if not _MEMORY_SCOPE.fullmatch(scope):
                raise ValueError(f"DEEP_PERMISSION_MEMORY_SCOPE_INVALID:{scope}")
        for agent in self.allowed_subagents:
            if not _NAME.fullmatch(agent):
                raise ValueError(f"DEEP_PERMISSION_SUBAGENT_INVALID:{agent}")
        if not set(self.memory_write_scopes) <= set(self.memory_read_scopes):
            raise ValueError("DEEP_PERMISSION_MEMORY_WRITE_ESCALATION")


@dataclass(frozen=True, slots=True)
class ResolvedSubagent:
    agent_id: str
    exact_version: str
    role: str
    description: str
    system_prompt: str
    model_profile: str
    allowed_tools: tuple[str, ...]
    skill_refs: tuple[str, ...] = ()
    output_schema: str = "AgentTaskResult"
    max_steps: int = 24
    provenance_ref: str = ""

    def __post_init__(self) -> None:
        _agent_id(self.agent_id)
        _version(self.exact_version, "DEEP_SUBAGENT_VERSION_INVALID")
        _text(self.role, 500, "DEEP_SUBAGENT_ROLE_INVALID")
        _text(self.description, 2_000, "DEEP_SUBAGENT_DESCRIPTION_INVALID")
        _text(self.system_prompt, _MAX_TEXT, "DEEP_SUBAGENT_PROMPT_INVALID")
        _version(self.model_profile, "DEEP_SUBAGENT_MODEL_PROFILE_INVALID")
        _tools(self.allowed_tools)
        if not 1 <= self.max_steps <= 128:
            raise ValueError("DEEP_SUBAGENT_MAX_STEPS_INVALID")
        if self.provenance_ref:
            _ref(self.provenance_ref, "DEEP_SUBAGENT_PROVENANCE_REF_INVALID")


@dataclass(frozen=True, slots=True)
class ResolvedAgentConfig:
    agent_id: str
    exact_version: str
    role: str
    system_prompt: str
    model_profile: str
    allowed_tools: tuple[str, ...]
    skill_refs: tuple[str, ...]
    context_policy: str
    memory_read_scopes: tuple[str, ...]
    memory_write_scopes: tuple[str, ...]
    sandbox_execute: bool
    subagents: tuple[ResolvedSubagent, ...]
    output_schema: str = "AgentTaskResult"
    max_steps: int = 64
    delegation: DelegationLimits = field(default_factory=DelegationLimits)
    provenance_ref: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        _agent_id(self.agent_id)
        _version(self.exact_version, "DEEP_AGENT_VERSION_INVALID")
        _text(self.role, 500, "DEEP_AGENT_ROLE_INVALID")
        _text(self.system_prompt, _MAX_TEXT, "DEEP_AGENT_PROMPT_INVALID")
        _version(self.model_profile, "DEEP_AGENT_MODEL_PROFILE_INVALID")
        _tools(self.allowed_tools)
        if not self.context_policy or len(self.context_policy) > 200:
            raise ValueError("DEEP_AGENT_CONTEXT_POLICY_INVALID")
        PermissionScope(
            allowed_tools=self.allowed_tools,
            sandbox_execute=self.sandbox_execute,
            memory_read_scopes=self.memory_read_scopes,
            memory_write_scopes=self.memory_write_scopes,
            allowed_subagents=tuple(item.agent_id for item in self.subagents),
        )
        if len(self.subagents) > self.delegation.max_children_per_agent:
            raise ValueError("DEEP_AGENT_CHILD_LIMIT_EXCEEDED")
        _unique(tuple(item.agent_id for item in self.subagents), "DEEP_AGENT_SUBAGENT_DUPLICATE")
        parent_tools = set(self.allowed_tools)
        for child in self.subagents:
            extra = set(child.allowed_tools) - parent_tools
            if extra:
                raise ValueError(
                    "DEEP_AGENT_SUBAGENT_TOOL_ESCALATION:"
                    f"{child.agent_id}:{','.join(sorted(extra))}"
                )
        if not 1 <= self.max_steps <= 256:
            raise ValueError("DEEP_AGENT_MAX_STEPS_INVALID")
        if self.provenance_ref:
            _ref(self.provenance_ref, "DEEP_AGENT_PROVENANCE_REF_INVALID")
        if self.content_hash and not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("DEEP_AGENT_CONTENT_HASH_INVALID")

    @property
    def identity(self) -> str:
        return f"{self.agent_id}@{self.exact_version}"


@dataclass(frozen=True, slots=True)
class MaterializedSkill:
    skill_id: str
    exact_version: str
    path: str
    content_hash: str
    required_tools: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    provenance_ref: str = ""

    def __post_init__(self) -> None:
        _agent_id(self.skill_id)
        _version(self.exact_version, "DEEP_SKILL_VERSION_INVALID")
        if not self.path.startswith("/skills/") or ".." in self.path.split("/"):
            raise ValueError("DEEP_SKILL_PATH_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("DEEP_SKILL_HASH_INVALID")
        _tools(self.required_tools)
        if self.provenance_ref:
            _ref(self.provenance_ref, "DEEP_SKILL_PROVENANCE_REF_INVALID")


@dataclass(frozen=True, slots=True)
class PinnedContextBundle:
    context_bundle_ref: str
    version: str
    pinned_constraints: str
    task_context: str
    source_refs: tuple[str, ...]
    content_hash: str

    def __post_init__(self) -> None:
        _ref(self.context_bundle_ref, "DEEP_CONTEXT_REF_INVALID")
        _version(self.version, "DEEP_CONTEXT_VERSION_INVALID")
        _text(self.pinned_constraints, 128_000, "DEEP_CONTEXT_PINNED_INVALID", allow_empty=True)
        _text(self.task_context, 128_000, "DEEP_CONTEXT_TASK_INVALID", allow_empty=True)
        for item in self.source_refs:
            _ref(item, "DEEP_CONTEXT_SOURCE_REF_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("DEEP_CONTEXT_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class DeepAgentInvocationContext:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    operation_id: UUID
    actor_id: str
    root_agent: str
    permissions: PermissionScope
    budget_limit_usd: str
    trace_id: str | None = None

    def __post_init__(self) -> None:
        _agent_id(self.root_agent)
        if not self.actor_id or len(self.actor_id) > 255:
            raise ValueError("DEEP_AGENT_ACTOR_INVALID")
        _money(self.budget_limit_usd)
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("DEEP_AGENT_TRACE_ID_INVALID")


@dataclass(frozen=True, slots=True)
class DeepAgentTaskRequest:
    agent_ref: str
    objective: str
    context_bundle_ref: str
    invocation: DeepAgentInvocationContext

    def __post_init__(self) -> None:
        if "@" not in self.agent_ref or len(self.agent_ref) > 180:
            raise ValueError("DEEP_TASK_AGENT_REF_INVALID")
        _text(self.objective, 64_000, "DEEP_TASK_OBJECTIVE_INVALID")
        _ref(self.context_bundle_ref, "DEEP_TASK_CONTEXT_REF_INVALID")


@dataclass(frozen=True, slots=True)
class AgentTaskResult:
    status: AgentTaskStatus
    summary: str
    decisions: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    proposed_operations: tuple[dict[str, Any], ...]
    open_questions: tuple[str, ...]
    confidence: str

    def __post_init__(self) -> None:
        _text(self.summary, 16_000, "DEEP_RESULT_SUMMARY_INVALID")
        for value in self.decisions + self.open_questions:
            _text(value, 4_000, "DEEP_RESULT_TEXT_INVALID", allow_empty=False)
        for value in self.artifact_refs + self.knowledge_refs:
            _ref(value, "DEEP_RESULT_REF_INVALID")
        for value in self.proposed_operations:
            _json_guard(value)
            if _contains_private_reasoning_key(value):
                raise ValueError("DEEP_RESULT_PRIVATE_REASONING_FORBIDDEN")
        try:
            confidence = Decimal(self.confidence)
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("DEEP_RESULT_CONFIDENCE_INVALID") from exc
        if not confidence.is_finite() or not Decimal("0") <= confidence <= Decimal("1"):
            raise ValueError("DEEP_RESULT_CONFIDENCE_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "summary": self.summary,
            "decisions": list(self.decisions),
            "artifact_refs": list(self.artifact_refs),
            "knowledge_refs": list(self.knowledge_refs),
            "proposed_operations": list(self.proposed_operations),
            "open_questions": list(self.open_questions),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class DeepAgentProvenance:
    agent_id: str
    agent_version: str
    agent_config_hash: str
    context_bundle_ref: str
    context_hash: str
    skill_versions: tuple[str, ...]
    tool_versions: tuple[str, ...]
    model_profile: str
    sandbox_execute: bool


@dataclass(frozen=True, slots=True)
class StoredAgentResult:
    result_ref: str
    result: AgentTaskResult
    provenance: DeepAgentProvenance

    def __post_init__(self) -> None:
        _ref(self.result_ref, "DEEP_RESULT_STORE_REF_INVALID")


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tools(values: tuple[str, ...]) -> None:
    _unique(values, "DEEP_TOOL_DUPLICATE")
    for value in values:
        if not _TOOL.fullmatch(value):
            raise ValueError(f"DEEP_TOOL_INVALID:{value}")


def _unique(values: tuple[str, ...], code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)


def _agent_id(value: str) -> None:
    if not _NAME.fullmatch(value):
        raise ValueError("DEEP_AGENT_ID_INVALID")


def _version(value: str, code: str) -> None:
    if not _VERSION.fullmatch(value):
        raise ValueError(code)


def _text(
    value: str,
    maximum: int,
    code: str,
    *,
    allow_empty: bool = False,
) -> None:
    if (not allow_empty and not value) or len(value) > maximum:
        raise ValueError(code)


def _money(value: str) -> None:
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("DEEP_AGENT_BUDGET_INVALID") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("DEEP_AGENT_BUDGET_INVALID")


def _ref(value: str, code: str) -> None:
    if not _REF.fullmatch(value):
        raise ValueError(code)


def _json_guard(value: Any, depth: int = 0) -> None:
    if depth > 24:
        raise ValueError("DEEP_JSON_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        if isinstance(value, str) and value.startswith("data:"):
            raise ValueError("DEEP_INLINE_DATA_URI_FORBIDDEN")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("DEEP_JSON_NONFINITE")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("DEEP_JSON_NON_STRING_KEY")
            _json_guard(child, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _json_guard(child, depth + 1)
        return
    raise ValueError(f"DEEP_JSON_UNSUPPORTED:{type(value).__name__}")


def _jsonable(value: Any) -> Any:
    _json_guard(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(child) for key, child in value.items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    return value


def _contains_private_reasoning_key(value: Any) -> bool:
    forbidden = {
        "reasoning",
        "chain_of_thought",
        "scratchpad",
        "hidden_thoughts",
        "raw_response",
    }
    if isinstance(value, dict):
        return any(
            key.casefold() in forbidden or _contains_private_reasoning_key(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_private_reasoning_key(child) for child in value)
    return False
