from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["OWNER", "ADMIN", "EDITOR", "VIEWER", "BILLING"]
Permission = Literal[
    "project.read",
    "project.write",
    "asset.upload",
    "artifact.approve",
    "brand.manage",
    "member.invite",
    "api_token.manage",
    "billing.read",
    "billing.manage",
    "admin.audit.read",
]

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    "OWNER": frozenset({
        "project.read","project.write","asset.upload","artifact.approve","brand.manage",
        "member.invite","api_token.manage","billing.read","billing.manage","admin.audit.read",
    }),
    "ADMIN": frozenset({
        "project.read","project.write","asset.upload","artifact.approve","brand.manage",
        "member.invite","api_token.manage","billing.read","admin.audit.read",
    }),
    "EDITOR": frozenset({"project.read","project.write","asset.upload","brand.manage"}),
    "VIEWER": frozenset({"project.read"}),
    "BILLING": frozenset({"project.read","billing.read","billing.manage"}),
}


@dataclass(frozen=True, slots=True)
class Membership:
    user_id: str
    organization_id: str
    role: Role
    active: bool = True


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    actor_id: str
    organization_id: str
    roles: tuple[Role, ...]
    permissions: frozenset[Permission]
    trace_id: str
    workspace_id: str | None = None


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    reason_code: str


def permissions_for_roles(roles: tuple[Role, ...]) -> frozenset[Permission]:
    permissions: set[Permission] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS[role])
    return frozenset(permissions)


def build_request_context(
    *,
    request_id: str,
    actor_id: str,
    organization_id: str,
    memberships: tuple[Membership, ...],
    trace_id: str,
    workspace_id: str | None = None,
) -> RequestContext:
    roles = tuple(
        membership.role
        for membership in memberships
        if membership.user_id == actor_id
        and membership.organization_id == organization_id
        and membership.active
    )
    if not roles:
        raise PermissionError("TENANT_NOT_FOUND_OR_FORBIDDEN")
    return RequestContext(
        request_id=request_id,
        actor_id=actor_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        roles=roles,
        permissions=permissions_for_roles(roles),
        trace_id=trace_id,
    )


def authorize(
    context: RequestContext,
    *,
    resource_organization_id: str,
    permission: Permission,
) -> AccessDecision:
    if resource_organization_id != context.organization_id:
        return AccessDecision(False, "TENANT_NOT_FOUND_OR_FORBIDDEN")
    if permission not in context.permissions:
        return AccessDecision(False, "PERMISSION_DENIED")
    return AccessDecision(True, "ALLOW")


def require_last_owner_invariant(
    memberships: tuple[Membership, ...],
    *,
    organization_id: str,
    target_user_id: str,
    target_role_after: Role | None,
) -> None:
    active_owners = {
        membership.user_id
        for membership in memberships
        if membership.organization_id == organization_id
        and membership.active
        and membership.role == "OWNER"
    }
    if target_user_id not in active_owners:
        return
    if target_role_after == "OWNER":
        return
    if len(active_owners) <= 1:
        raise ValueError("LAST_OWNER_REQUIRED")
