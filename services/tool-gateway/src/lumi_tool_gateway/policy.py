from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .contracts import (
    ApprovalDecision,
    ToolApproval,
    ToolDefinition,
    ToolPermissionContext,
    ToolRisk,
)
from .errors import ToolPermissionDeniedError


@dataclass(frozen=True, slots=True)
class ToolPolicyDecision:
    allowed: bool
    reason_code: str


class ToolPermissionPolicy:
    """Default-deny tool authorization with parent/subagent non-escalation."""

    def authorize(
        self,
        definition: ToolDefinition,
        context: ToolPermissionContext,
    ) -> ToolPolicyDecision:
        if any(
            _matches(definition.name, pattern)
            for pattern in context.organization_deny_patterns
        ):
            return ToolPolicyDecision(False, "ORG_TOOL_DENIED")
        if context.organization_allow_patterns and not any(
            _matches(definition.name, pattern)
            for pattern in context.organization_allow_patterns
        ):
            return ToolPolicyDecision(False, "ORG_TOOL_NOT_ALLOWED")
        if not any(
            _matches(definition.name, pattern)
            for pattern in context.agent_allow_patterns
        ):
            return ToolPolicyDecision(False, "AGENT_TOOL_NOT_ALLOWED")
        if context.parent_allow_patterns is not None and not any(
            _matches(definition.name, pattern)
            for pattern in context.parent_allow_patterns
        ):
            return ToolPolicyDecision(False, "SUBAGENT_PERMISSION_ESCALATION")
        missing = definition.permissions - context.granted_permissions
        if missing:
            names = ",".join(sorted(missing))
            return ToolPolicyDecision(False, f"TOOL_PERMISSION_MISSING:{names}")
        return ToolPolicyDecision(True, "ALLOW")

    def require(
        self,
        definition: ToolDefinition,
        context: ToolPermissionContext,
    ) -> None:
        decision = self.authorize(definition, context)
        if not decision.allowed:
            raise ToolPermissionDeniedError(decision.reason_code)


class ToolApprovalPolicy:
    def __init__(
        self,
        *,
        approval_required_risks: frozenset[ToolRisk] | None = None,
    ) -> None:
        self.approval_required_risks = approval_required_risks or frozenset(
            {
                ToolRisk.WRITE_EXTERNAL,
                ToolRisk.DESTRUCTIVE,
                ToolRisk.FINANCIAL,
                ToolRisk.PRIVILEGED,
            }
        )

    def decision(self, definition: ToolDefinition) -> ToolApproval:
        if definition.risk in self.approval_required_risks:
            return ToolApproval(
                ApprovalDecision.REQUIRED,
                reason_code=f"RISK_REQUIRES_APPROVAL:{definition.risk.value}",
            )
        return ToolApproval(
            ApprovalDecision.NOT_REQUIRED,
            reason_code="APPROVAL_NOT_REQUIRED",
        )


def _matches(tool_name: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    return fnmatch.fnmatchcase(tool_name, pattern)
