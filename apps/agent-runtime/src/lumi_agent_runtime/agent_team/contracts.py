from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from lumi_agent_runtime.agent_registry.definition import AgentDefinition


class AgentArchetype(StrEnum):
    DIALOG = "dialog"
    DEEP = "deep"
    GENERATOR_WORKER = "generator-worker"
    CRITIC = "critic"


class TeamTaskStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class TeamArtifactRef:
    artifact_id: str
    version: str
    kind: str

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.version or not self.kind:
            raise ValueError("AGENT_TEAM_ARTIFACT_REF_INVALID")


@dataclass(frozen=True, slots=True)
class TeamCitationRef:
    source_type: str
    source_id: str
    version: str
    locator: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_type or not self.source_id or not self.version:
            raise ValueError("AGENT_TEAM_CITATION_REF_INVALID")
        _json_guard(self.locator, "$.locator")


@dataclass(frozen=True, slots=True)
class TeamTaskInput:
    objective: str
    inputs: dict[str, Any]
    constraints: tuple[str, ...]
    expected_output: str
    deadline_at: datetime | None = None
    budget_remaining_usd: float | None = None
    parent_task_id: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.objective.strip() or not self.expected_output.strip():
            raise ValueError("AGENT_TEAM_TASK_INPUT_INVALID")
        if self.budget_remaining_usd is not None and self.budget_remaining_usd < 0:
            raise ValueError("AGENT_TEAM_TASK_BUDGET_INVALID")
        if len(self.constraints) > 128:
            raise ValueError("AGENT_TEAM_TASK_CONSTRAINTS_TOO_LARGE")
        _json_guard(self.inputs, "$.inputs")


@dataclass(frozen=True, slots=True)
class TeamTaskResult:
    status: TeamTaskStatus
    summary: str
    artifacts: tuple[TeamArtifactRef, ...] = ()
    citations: tuple[TeamCitationRef, ...] = ()
    confidence: float = 0.0
    warnings: tuple[str, ...] = ()
    followups: tuple[str, ...] = ()
    waiting_reason: str | None = None
    structured_output: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("AGENT_TEAM_TASK_RESULT_SUMMARY_REQUIRED")
        if not 0 <= self.confidence <= 1:
            raise ValueError("AGENT_TEAM_TASK_RESULT_CONFIDENCE_INVALID")
        waiting = self.status in {
            TeamTaskStatus.WAITING_EXTERNAL,
            TeamTaskStatus.WAITING_APPROVAL,
        }
        if waiting != bool(self.waiting_reason):
            raise ValueError("AGENT_TEAM_WAITING_REASON_CONTRACT_INVALID")
        _json_guard(self.structured_output, "$.structured_output")


@dataclass(frozen=True, slots=True)
class AgentTeamProfile:
    archetype: AgentArchetype
    objective: str
    can_delegate: bool
    delegation_allowlist: tuple[str, ...]
    max_delegation_depth: int
    delegation_tool_ceiling: frozenset[str]
    delegation_permission_ceiling: frozenset[str]
    timeout_profile: str
    risk_profile: str
    approval_gated_actions: tuple[str, ...] = ()
    supports_waiting_external: bool = False

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("AGENT_TEAM_OBJECTIVE_REQUIRED")
        if not 0 <= self.max_delegation_depth <= 5:
            raise ValueError("AGENT_TEAM_DELEGATION_DEPTH_INVALID")
        if not self.can_delegate and (
            self.delegation_allowlist or self.max_delegation_depth != 0
        ):
            raise ValueError("AGENT_TEAM_NON_DELEGATOR_HAS_DELEGATION_CONFIG")
        if self.can_delegate and not self.delegation_allowlist:
            raise ValueError("AGENT_TEAM_DELEGATION_ALLOWLIST_REQUIRED")
        if self.timeout_profile not in {
            "interactive",
            "standard",
            "long-running",
            "external",
        }:
            raise ValueError("AGENT_TEAM_TIMEOUT_PROFILE_INVALID")
        if self.risk_profile not in {
            "read-only",
            "internal-write",
            "media-write",
            "approval-gated",
        }:
            raise ValueError("AGENT_TEAM_RISK_PROFILE_INVALID")


@dataclass(frozen=True, slots=True)
class DelegationGrant:
    parent_agent: str
    child_agent: str
    allowed_tools: frozenset[str]
    granted_permissions: frozenset[str]
    remaining_depth: int
    budget_remaining_usd: float | None
    deadline_at: datetime | None


def team_profile(definition: AgentDefinition) -> AgentTeamProfile:
    raw = definition.metadata.get("team")
    if not isinstance(raw, dict):
        raise ValueError(f"AGENT_TEAM_PROFILE_MISSING:{definition.agent_id}")
    allowed_keys = {
        "archetype",
        "objective",
        "can_delegate",
        "delegation_allowlist",
        "max_delegation_depth",
        "delegation_tool_ceiling",
        "delegation_permission_ceiling",
        "timeout_profile",
        "risk_profile",
        "approval_gated_actions",
        "supports_waiting_external",
    }
    unknown = set(raw) - allowed_keys
    if unknown:
        raise ValueError(
            f"AGENT_TEAM_PROFILE_UNKNOWN_FIELDS:{definition.agent_id}:"
            + ",".join(sorted(unknown))
        )
    profile = AgentTeamProfile(
        archetype=AgentArchetype(str(raw["archetype"])),
        objective=str(raw["objective"]),
        can_delegate=bool(raw["can_delegate"]),
        delegation_allowlist=_string_tuple(raw.get("delegation_allowlist", [])),
        max_delegation_depth=int(raw.get("max_delegation_depth", 0)),
        delegation_tool_ceiling=frozenset(
            _string_tuple(raw.get("delegation_tool_ceiling", []))
        ),
        delegation_permission_ceiling=frozenset(
            _string_tuple(raw.get("delegation_permission_ceiling", []))
        ),
        timeout_profile=str(raw["timeout_profile"]),
        risk_profile=str(raw["risk_profile"]),
        approval_gated_actions=_string_tuple(raw.get("approval_gated_actions", [])),
        supports_waiting_external=bool(raw.get("supports_waiting_external", False)),
    )
    if set(definition.allowed_tools) - profile.delegation_tool_ceiling:
        raise ValueError(
            f"AGENT_TEAM_DIRECT_TOOL_OUTSIDE_CEILING:{definition.agent_id}"
        )
    if set(definition.permissions) - profile.delegation_permission_ceiling:
        raise ValueError(
            f"AGENT_TEAM_DIRECT_PERMISSION_OUTSIDE_CEILING:{definition.agent_id}"
        )
    return profile


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("AGENT_TEAM_STRING_LIST_REQUIRED")
    items = tuple(str(item) for item in value)
    if any(not item.strip() for item in items) or len(items) != len(set(items)):
        raise ValueError("AGENT_TEAM_STRING_LIST_INVALID")
    return items


def _json_guard(value: Any, path: str, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError(f"AGENT_TEAM_JSON_DEPTH_EXCEEDED:{path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        if len(value) > 512:
            raise ValueError(f"AGENT_TEAM_JSON_LIST_TOO_LARGE:{path}")
        for index, item in enumerate(value):
            _json_guard(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 256:
            raise ValueError(f"AGENT_TEAM_JSON_OBJECT_TOO_LARGE:{path}")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise ValueError(f"AGENT_TEAM_JSON_KEY_INVALID:{path}")
            _json_guard(item, f"{path}.{key}", depth + 1)
        return
    raise ValueError(f"AGENT_TEAM_JSON_TYPE_INVALID:{path}")
