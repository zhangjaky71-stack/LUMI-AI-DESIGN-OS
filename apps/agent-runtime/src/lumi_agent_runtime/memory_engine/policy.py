from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    MemoryAccessContext,
    MemoryActorType,
    MemoryCandidate,
    MemoryCandidateOutcome,
    MemoryKind,
    MemoryScope,
)


@dataclass(frozen=True, slots=True)
class MemoryPolicyDecision:
    allowed: bool
    outcome: MemoryCandidateOutcome
    reason: str


def scope_matches_access(
    candidate: MemoryCandidate,
    access: MemoryAccessContext,
) -> bool:
    if candidate.organization_id != access.organization_id:
        return False
    expected = _expected_scope_id(candidate.scope_type, access)
    return expected is not None and candidate.scope_id == expected


def evaluate_write_policy(
    candidate: MemoryCandidate,
    access: MemoryAccessContext,
) -> MemoryPolicyDecision:
    if candidate.organization_id != access.organization_id:
        return MemoryPolicyDecision(
            False,
            MemoryCandidateOutcome.REJECT_SCOPE,
            "MEMORY_CROSS_TENANT_DENIED",
        )
    if (
        candidate.created_by_type != access.actor_type
        or candidate.created_by_id != access.actor_id
    ):
        return MemoryPolicyDecision(
            False,
            MemoryCandidateOutcome.REJECT_SCOPE,
            "MEMORY_ACTOR_SPOOF_DENIED",
        )
    if not scope_matches_access(candidate, access):
        return MemoryPolicyDecision(
            False,
            MemoryCandidateOutcome.REJECT_SCOPE,
            "MEMORY_SCOPE_ID_DENIED",
        )

    if access.actor_type == MemoryActorType.SYSTEM:
        if _is_brand_rule_proposal(candidate):
            return MemoryPolicyDecision(
                True,
                MemoryCandidateOutcome.BRAND_RULE_PROPOSAL,
                "MEMORY_BRAND_RULE_PROPOSAL",
            )
        return MemoryPolicyDecision(
            True,
            MemoryCandidateOutcome.WRITE,
            "MEMORY_SYSTEM_WRITE_ALLOWED",
        )

    if access.actor_type == MemoryActorType.AGENT:
        if candidate.scope_type not in {
            MemoryScope.SESSION,
            MemoryScope.PROJECT,
            MemoryScope.AGENT,
            MemoryScope.BRAND,
        }:
            return MemoryPolicyDecision(
                False,
                MemoryCandidateOutcome.REJECT_SCOPE,
                "MEMORY_AGENT_SCOPE_DENIED",
            )
        if candidate.scope_type == MemoryScope.BRAND:
            if _is_brand_rule_proposal(candidate):
                return MemoryPolicyDecision(
                    True,
                    MemoryCandidateOutcome.BRAND_RULE_PROPOSAL,
                    "MEMORY_BRAND_RULE_PROPOSAL",
                )
            return MemoryPolicyDecision(
                False,
                MemoryCandidateOutcome.REJECT_SCOPE,
                "MEMORY_AGENT_BRAND_WRITE_DENIED",
            )
        return MemoryPolicyDecision(
            True,
            MemoryCandidateOutcome.WRITE,
            "MEMORY_AGENT_WRITE_ALLOWED",
        )

    if access.actor_type == MemoryActorType.USER:
        if candidate.scope_type not in {
            MemoryScope.SESSION,
            MemoryScope.USER,
            MemoryScope.PROJECT,
            MemoryScope.BRAND,
        }:
            return MemoryPolicyDecision(
                False,
                MemoryCandidateOutcome.REJECT_SCOPE,
                "MEMORY_USER_SCOPE_DENIED",
            )
        if candidate.scope_type == MemoryScope.BRAND:
            if _is_brand_rule_proposal(candidate):
                return MemoryPolicyDecision(
                    True,
                    MemoryCandidateOutcome.BRAND_RULE_PROPOSAL,
                    "MEMORY_BRAND_RULE_PROPOSAL",
                )
            return MemoryPolicyDecision(
                False,
                MemoryCandidateOutcome.REJECT_SCOPE,
                "MEMORY_USER_BRAND_WRITE_DENIED",
            )
        return MemoryPolicyDecision(
            True,
            MemoryCandidateOutcome.WRITE,
            "MEMORY_USER_WRITE_ALLOWED",
        )

    return MemoryPolicyDecision(
        False,
        MemoryCandidateOutcome.REJECT_SCOPE,
        "MEMORY_ACTOR_UNKNOWN",
    )


def can_read_scope(
    scope_type: MemoryScope,
    scope_id: str,
    access: MemoryAccessContext,
) -> bool:
    if access.actor_type == MemoryActorType.SYSTEM:
        return (
            _expected_scope_id(scope_type, access) == scope_id
            or scope_type == MemoryScope.ORGANIZATION
        )
    if scope_type == MemoryScope.ORGANIZATION:
        return (
            "memory.organization.read" in access.granted_permissions
            and scope_id == str(access.organization_id)
        )
    if scope_type == MemoryScope.BRAND:
        return access.brand_id is not None and scope_id == str(access.brand_id)
    if scope_type == MemoryScope.PROJECT:
        return access.project_id is not None and scope_id == str(access.project_id)
    if scope_type == MemoryScope.USER:
        return access.user_id is not None and scope_id == str(access.user_id)
    if scope_type == MemoryScope.AGENT:
        return access.agent_key is not None and scope_id == access.agent_key
    if scope_type == MemoryScope.SESSION:
        return access.session_id is not None and scope_id == access.session_id
    return False


def can_delete_scope(
    scope_type: MemoryScope,
    scope_id: str,
    access: MemoryAccessContext,
) -> bool:
    if access.actor_type == MemoryActorType.SYSTEM:
        return can_read_scope(scope_type, scope_id, access)
    if access.actor_type == MemoryActorType.USER:
        if scope_type == MemoryScope.USER:
            return access.user_id is not None and scope_id == str(access.user_id)
        if scope_type == MemoryScope.PROJECT:
            return (
                "memory.project.delete" in access.granted_permissions
                and can_read_scope(scope_type, scope_id, access)
            )
        return False
    if access.actor_type == MemoryActorType.AGENT:
        if scope_type in {MemoryScope.SESSION, MemoryScope.AGENT}:
            return can_read_scope(scope_type, scope_id, access)
        if scope_type == MemoryScope.PROJECT:
            return (
                "memory.project.delete" in access.granted_permissions
                and can_read_scope(scope_type, scope_id, access)
            )
        return False
    return False


def _expected_scope_id(
    scope_type: MemoryScope,
    access: MemoryAccessContext,
) -> str | None:
    mapping = {
        MemoryScope.ORGANIZATION: str(access.organization_id),
        MemoryScope.PROJECT: str(access.project_id) if access.project_id else None,
        MemoryScope.USER: str(access.user_id) if access.user_id else None,
        MemoryScope.BRAND: str(access.brand_id) if access.brand_id else None,
        MemoryScope.AGENT: access.agent_key,
        MemoryScope.SESSION: access.session_id,
    }
    return mapping[scope_type]


def _is_brand_rule_proposal(candidate: MemoryCandidate) -> bool:
    return (
        candidate.scope_type == MemoryScope.BRAND
        and candidate.kind == MemoryKind.CONSTRAINT_PREFERENCE
    )
