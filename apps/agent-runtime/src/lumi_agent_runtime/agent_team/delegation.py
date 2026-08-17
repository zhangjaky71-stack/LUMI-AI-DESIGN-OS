from __future__ import annotations

from collections.abc import Mapping

from .contracts import DelegationGrant, DelegationRequest, TeamRoleDefinition, TeamRoleKind


class DelegationPolicy:
    def __init__(self, roles: Mapping[str, TeamRoleDefinition]) -> None:
        self._roles = roles
        self._validate_graph()

    def authorize(self, request: DelegationRequest) -> DelegationGrant:
        try:
            parent = self._roles[request.parent_agent_id]
            child = self._roles[request.child_agent_id]
        except KeyError as exc:
            raise PermissionError("AGENT_TEAM_DELEGATION_UNKNOWN_AGENT") from exc
        if parent.role_kind is not TeamRoleKind.DIRECTOR:
            raise PermissionError("AGENT_TEAM_SPECIALIST_DELEGATION_FORBIDDEN")
        if not parent.can_delegate or child.agent_id not in parent.delegation_allowlist:
            raise PermissionError("AGENT_TEAM_DELEGATION_TARGET_DENIED")
        if request.remaining_depth < 1 or parent.max_delegation_depth < 1:
            raise PermissionError("AGENT_TEAM_DELEGATION_DEPTH_EXHAUSTED")

        child_tools = frozenset(child.direct_tools)
        effective = child_tools & request.invocation_tools
        if not effective and child_tools:
            raise PermissionError("AGENT_TEAM_DELEGATION_NO_EFFECTIVE_TOOLS")
        if not effective <= request.invocation_tools:
            raise PermissionError("AGENT_TEAM_DELEGATION_INVOCATION_ESCALATION")
        if not effective <= child_tools:
            raise PermissionError("AGENT_TEAM_DELEGATION_ROLE_ESCALATION")
        return DelegationGrant(
            parent_agent_id=parent.agent_id,
            child_agent_id=child.agent_id,
            effective_tools=effective,
            remaining_depth=request.remaining_depth - 1,
            budget_remaining_usd=request.budget_remaining_usd,
        )

    def _validate_graph(self) -> None:
        directors = [role for role in self._roles.values() if role.role_kind is TeamRoleKind.DIRECTOR]
        if len(directors) != 1:
            raise ValueError("AGENT_TEAM_SINGLE_DIRECTOR_REQUIRED")
        director = directors[0]
        expected = set(self._roles) - {director.agent_id}
        if set(director.delegation_allowlist) != expected:
            raise ValueError("AGENT_TEAM_DIRECTOR_ALLOWLIST_INCOMPLETE")
        for role in self._roles.values():
            if role.agent_id == director.agent_id:
                continue
            if role.can_delegate or role.delegation_allowlist or role.max_delegation_depth:
                raise ValueError("AGENT_TEAM_SPECIALIST_DELEGATION_MUST_BE_DISABLED")
