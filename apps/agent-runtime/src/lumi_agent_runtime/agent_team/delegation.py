from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from lumi_agent_runtime.agent_registry.definition import AgentDefinition

from .contracts import AgentTeamProfile, DelegationGrant, team_profile


@dataclass(frozen=True, slots=True)
class DelegationRuntimeContext:
    allowed_tools: frozenset[str]
    granted_permissions: frozenset[str]
    depth: int
    budget_remaining_usd: float | None = None
    deadline_at: datetime | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("AGENT_TEAM_RUNTIME_DEPTH_INVALID")
        if self.budget_remaining_usd is not None and self.budget_remaining_usd < 0:
            raise ValueError("AGENT_TEAM_RUNTIME_BUDGET_INVALID")


def authorize_delegation(
    *,
    parent: AgentDefinition,
    child: AgentDefinition,
    runtime: DelegationRuntimeContext,
) -> DelegationGrant:
    parent_profile = team_profile(parent)
    child_profile = team_profile(child)
    if runtime.cancelled:
        raise PermissionError("AGENT_TEAM_DELEGATION_CANCELLED")
    if not parent_profile.can_delegate:
        raise PermissionError("AGENT_TEAM_PARENT_CANNOT_DELEGATE")
    if child.agent_id not in parent_profile.delegation_allowlist:
        raise PermissionError("AGENT_TEAM_CHILD_NOT_ALLOWLISTED")
    if runtime.depth >= parent_profile.max_delegation_depth:
        raise PermissionError("AGENT_TEAM_DELEGATION_DEPTH_EXCEEDED")

    parent_tool_ceiling = parent_profile.delegation_tool_ceiling & runtime.allowed_tools
    parent_permission_ceiling = (
        parent_profile.delegation_permission_ceiling & runtime.granted_permissions
    )
    child_tools = frozenset(child.allowed_tools)
    child_permissions = frozenset(child.permissions)
    if not child_tools <= parent_tool_ceiling:
        raise PermissionError("AGENT_TEAM_CHILD_TOOL_ESCALATION")
    if not child_permissions <= parent_permission_ceiling:
        raise PermissionError("AGENT_TEAM_CHILD_PERMISSION_ESCALATION")

    # A child may delegate only inside its own declared profile. The parent grant
    # never silently enlarges the child's own ceiling.
    if child_profile.can_delegate:
        if not child_profile.delegation_tool_ceiling <= parent_tool_ceiling:
            raise PermissionError("AGENT_TEAM_CHILD_DELEGATION_TOOL_CEILING_ESCALATION")
        if not child_profile.delegation_permission_ceiling <= parent_permission_ceiling:
            raise PermissionError(
                "AGENT_TEAM_CHILD_DELEGATION_PERMISSION_CEILING_ESCALATION"
            )

    return DelegationGrant(
        parent_agent=parent.agent_id,
        child_agent=child.agent_id,
        allowed_tools=child_tools,
        granted_permissions=child_permissions,
        remaining_depth=parent_profile.max_delegation_depth - runtime.depth - 1,
        budget_remaining_usd=runtime.budget_remaining_usd,
        deadline_at=runtime.deadline_at,
    )


def validate_team_delegation_graph(
    definitions: Mapping[str, AgentDefinition],
) -> None:
    for agent_id, definition in definitions.items():
        profile = team_profile(definition)
        for child_id in profile.delegation_allowlist:
            child = definitions.get(child_id)
            if child is None:
                raise ValueError(f"AGENT_TEAM_UNKNOWN_DELEGATE:{agent_id}:{child_id}")
            child_profile = team_profile(child)
            if not set(child.allowed_tools) <= profile.delegation_tool_ceiling:
                raise ValueError(
                    f"AGENT_TEAM_STATIC_CHILD_TOOL_ESCALATION:{agent_id}:{child_id}"
                )
            if not set(child.permissions) <= profile.delegation_permission_ceiling:
                raise ValueError(
                    f"AGENT_TEAM_STATIC_CHILD_PERMISSION_ESCALATION:{agent_id}:{child_id}"
                )
            if child_profile.can_delegate:
                if not child_profile.delegation_tool_ceiling <= profile.delegation_tool_ceiling:
                    raise ValueError(
                        "AGENT_TEAM_STATIC_NESTED_TOOL_CEILING_ESCALATION:"
                        f"{agent_id}:{child_id}"
                    )
                if not child_profile.delegation_permission_ceiling <= (
                    profile.delegation_permission_ceiling
                ):
                    raise ValueError(
                        "AGENT_TEAM_STATIC_NESTED_PERMISSION_CEILING_ESCALATION:"
                        f"{agent_id}:{child_id}"
                    )
