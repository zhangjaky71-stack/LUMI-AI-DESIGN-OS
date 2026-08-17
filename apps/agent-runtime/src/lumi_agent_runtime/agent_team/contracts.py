from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from lumi_agent_runtime.agent_registry.contracts import AgentManifest
from lumi_agent_runtime.deep_runtime.contracts import DelegationLimits

_AGENT_ID = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_.-]{0,255}$")
_SKILL_REF = re.compile(r"^[a-z][a-z0-9_-]{0,62}@[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")


class TeamRoleKind(StrEnum):
    DIRECTOR = "director"
    PRODUCER = "producer"
    CRITIC = "critic"
    VALIDATOR = "validator"
    PLANNER = "planner"


class HandoffStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    NEEDS_INPUT = "needs_input"
    WAITING_APPROVAL = "waiting_approval"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TeamRoleDefinition:
    agent_id: str
    role: str
    description: str
    role_kind: TeamRoleKind
    model_profile: str
    context_policy: str
    direct_tools: tuple[str, ...]
    skill_refs: tuple[str, ...]
    memory_read_scopes: tuple[str, ...] = ()
    memory_write_scopes: tuple[str, ...] = ()
    can_delegate: bool = False
    delegation_allowlist: tuple[str, ...] = ()
    max_delegation_depth: int = 0
    approval_gated_actions: tuple[str, ...] = ()
    produces_artifacts: bool = False
    may_approve_own_output: bool = False
    system_prompt: str = ""

    def __post_init__(self) -> None:
        if not _AGENT_ID.fullmatch(self.agent_id):
            raise ValueError("AGENT_TEAM_AGENT_ID_INVALID")
        if not self.role.strip() or not self.description.strip():
            raise ValueError("AGENT_TEAM_ROLE_TEXT_REQUIRED")
        if not self.system_prompt.strip():
            raise ValueError("AGENT_TEAM_SYSTEM_PROMPT_REQUIRED")
        if not self.model_profile or len(self.model_profile) > 100:
            raise ValueError("AGENT_TEAM_MODEL_PROFILE_INVALID")
        if not self.context_policy or len(self.context_policy) > 200:
            raise ValueError("AGENT_TEAM_CONTEXT_POLICY_INVALID")
        _unique(self.direct_tools, "AGENT_TEAM_TOOL_DUPLICATE")
        _unique(self.skill_refs, "AGENT_TEAM_SKILL_DUPLICATE")
        _unique(self.delegation_allowlist, "AGENT_TEAM_DELEGATE_DUPLICATE")
        for tool in self.direct_tools:
            if not _TOOL.fullmatch(tool):
                raise ValueError(f"AGENT_TEAM_TOOL_INVALID:{tool}")
        for ref in self.skill_refs:
            if not _SKILL_REF.fullmatch(ref):
                raise ValueError(f"AGENT_TEAM_SKILL_REF_INVALID:{ref}")
        for target in self.delegation_allowlist:
            if not _AGENT_ID.fullmatch(target):
                raise ValueError(f"AGENT_TEAM_DELEGATE_INVALID:{target}")
        if not 0 <= self.max_delegation_depth <= 4:
            raise ValueError("AGENT_TEAM_DELEGATION_DEPTH_INVALID")
        if self.can_delegate != bool(self.delegation_allowlist):
            raise ValueError("AGENT_TEAM_DELEGATION_ALLOWLIST_CONTRACT_INVALID")
        if not self.can_delegate and self.max_delegation_depth != 0:
            raise ValueError("AGENT_TEAM_NON_DELEGATOR_DEPTH_INVALID")
        if self.may_approve_own_output and self.role_kind in {
            TeamRoleKind.PRODUCER,
            TeamRoleKind.CRITIC,
        }:
            raise ValueError("AGENT_TEAM_SELF_APPROVAL_FORBIDDEN")

    def to_agent_manifest(self, *, version: str = "1.0.0") -> AgentManifest:
        return AgentManifest(
            agent_id=self.agent_id,
            version=version,
            role=self.role,
            description=self.description,
            system_prompt=self.system_prompt,
            model_profile=self.model_profile,
            allowed_tools=self.direct_tools,
            skill_refs=self.skill_refs,
            context_policy=self.context_policy,
            memory_read_scopes=self.memory_read_scopes,
            memory_write_scopes=self.memory_write_scopes,
            sandbox_execute=False,
            subagent_refs=(),
            output_schema="TeamHandoffEnvelope",
            max_steps=64 if self.role_kind is TeamRoleKind.DIRECTOR else 32,
            delegation=DelegationLimits(
                max_depth=0,
                max_total_subagent_calls=0,
                max_parallel_subagents=1,
                max_children_per_agent=0,
            ),
        )


@dataclass(frozen=True, slots=True)
class TeamHandoffEnvelope:
    status: HandoffStatus
    summary: str
    structured_output: Mapping[str, Any]
    artifact_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    proposed_operations: tuple[Mapping[str, Any], ...] = ()
    risks: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    confidence: float = 0.0
    producer_agent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.summary.strip() or len(self.summary) > 16_000:
            raise ValueError("AGENT_TEAM_HANDOFF_SUMMARY_INVALID")
        if not isinstance(self.confidence, int | float) or not math.isfinite(self.confidence):
            raise ValueError("AGENT_TEAM_HANDOFF_CONFIDENCE_INVALID")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("AGENT_TEAM_HANDOFF_CONFIDENCE_INVALID")
        _unique(self.artifact_refs, "AGENT_TEAM_ARTIFACT_REF_DUPLICATE")
        _unique(self.knowledge_refs, "AGENT_TEAM_KNOWLEDGE_REF_DUPLICATE")
        for ref in self.artifact_refs + self.knowledge_refs:
            if not _REF.fullmatch(ref):
                raise ValueError(f"AGENT_TEAM_HANDOFF_REF_INVALID:{ref}")
        if self.producer_agent_id is not None and not _AGENT_ID.fullmatch(self.producer_agent_id):
            raise ValueError("AGENT_TEAM_PRODUCER_ID_INVALID")
        _json_guard(self.structured_output)
        for operation in self.proposed_operations:
            _json_guard(operation)


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    parent_agent_id: str
    child_agent_id: str
    invocation_tools: frozenset[str]
    remaining_depth: int
    objective: str
    budget_remaining_usd: float | None = None

    def __post_init__(self) -> None:
        for value in (self.parent_agent_id, self.child_agent_id):
            if not _AGENT_ID.fullmatch(value):
                raise ValueError("AGENT_TEAM_DELEGATION_AGENT_INVALID")
        if self.remaining_depth < 0:
            raise ValueError("AGENT_TEAM_DELEGATION_DEPTH_INVALID")
        if not self.objective.strip() or len(self.objective) > 64_000:
            raise ValueError("AGENT_TEAM_DELEGATION_OBJECTIVE_INVALID")
        if self.budget_remaining_usd is not None and self.budget_remaining_usd < 0:
            raise ValueError("AGENT_TEAM_DELEGATION_BUDGET_INVALID")
        for tool in self.invocation_tools:
            if not _TOOL.fullmatch(tool):
                raise ValueError("AGENT_TEAM_INVOCATION_TOOL_INVALID")


@dataclass(frozen=True, slots=True)
class DelegationGrant:
    parent_agent_id: str
    child_agent_id: str
    effective_tools: frozenset[str]
    remaining_depth: int
    budget_remaining_usd: float | None


def _json_guard(value: Any, depth: int = 0) -> None:
    if depth > 20:
        raise ValueError("AGENT_TEAM_JSON_TOO_DEEP")
    if value is None or isinstance(value, str | int | bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("AGENT_TEAM_JSON_NONFINITE")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("AGENT_TEAM_JSON_KEY_INVALID")
            _json_guard(child, depth + 1)
        return
    if isinstance(value, tuple | list):
        for child in value:
            _json_guard(child, depth + 1)
        return
    raise ValueError(f"AGENT_TEAM_JSON_TYPE_INVALID:{type(value).__name__}")


def _unique(values: tuple[Any, ...], code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)
