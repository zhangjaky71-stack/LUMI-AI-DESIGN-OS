from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from .models import ActorType, OrganizationMembership, OrganizationRole, Principal


class Permission(StrEnum):
    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"
    ASSET_UPLOAD = "asset.upload"
    ARTIFACT_APPROVE = "artifact.approve"
    BRAND_MANAGE = "brand.manage"
    MEMBER_INVITE = "member.invite"
    MEMBER_MANAGE = "member.manage"
    BILLING_READ = "billing.read"
    BILLING_MANAGE = "billing.manage"
    ADMIN_AUDIT_READ = "admin.audit.read"
    AUDIT_EXPORT = "audit.export"
    GOVERNANCE_MANAGE = "governance.manage"
    API_TOKEN_MANAGE = "api_token.manage"


_ROLE_PERMISSIONS: dict[OrganizationRole, frozenset[Permission]] = {
    OrganizationRole.OWNER: frozenset(Permission),
    OrganizationRole.ADMIN: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.ASSET_UPLOAD,
            Permission.ARTIFACT_APPROVE,
            Permission.BRAND_MANAGE,
            Permission.MEMBER_INVITE,
            Permission.MEMBER_MANAGE,
            Permission.BILLING_READ,
            Permission.ADMIN_AUDIT_READ,
            Permission.API_TOKEN_MANAGE,
        }
    ),
    OrganizationRole.EDITOR: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.ASSET_UPLOAD,
            Permission.ARTIFACT_APPROVE,
        }
    ),
    OrganizationRole.VIEWER: frozenset({Permission.PROJECT_READ}),
    OrganizationRole.BILLING: frozenset(
        {Permission.BILLING_READ, Permission.BILLING_MANAGE}
    ),
}


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    reason_code: str


class AccessPolicyService:
    def permissions_for_roles(
        self, roles: tuple[OrganizationRole, ...]
    ) -> tuple[Permission, ...]:
        permissions: set[Permission] = set()
        for role in roles:
            permissions.update(_ROLE_PERMISSIONS[role])
        return tuple(sorted(permissions, key=str))

    def principal_for_memberships(
        self,
        *,
        actor_id: str,
        user_id: UUID,
        organization_id: UUID,
        memberships: tuple[OrganizationMembership, ...],
    ) -> Principal | None:
        roles = tuple(
            sorted(
                {
                    membership.role
                    for membership in memberships
                    if membership.user_id == user_id
                    and membership.organization_id == organization_id
                },
                key=str,
            )
        )
        if not roles:
            return None
        permissions = self.permissions_for_roles(roles)
        return Principal(
            actor_type=ActorType.USER,
            actor_id=actor_id,
            user_id=user_id,
            organization_id=organization_id,
            roles=tuple(role.value for role in roles),
            permissions=tuple(permission.value for permission in permissions),
        )

    def authorize(
        self,
        principal: Principal,
        *,
        organization_id: UUID,
        permission: Permission | str,
    ) -> AccessDecision:
        if principal.organization_id != organization_id:
            return AccessDecision(False, "TENANT_RESOURCE_NOT_FOUND")
        permission_value = (
            permission.value if isinstance(permission, Permission) else permission
        )
        if permission_value not in principal.permissions:
            return AccessDecision(False, "PERMISSION_DENIED")
        return AccessDecision(True, "ALLOW")


def enforce_last_owner_invariant(
    memberships: tuple[OrganizationMembership, ...],
    *,
    target_membership_id: UUID,
    new_role: OrganizationRole | None,
) -> None:
    target = next(
        (
            membership
            for membership in memberships
            if membership.id == target_membership_id
        ),
        None,
    )
    if target is None or target.role != OrganizationRole.OWNER:
        return
    if new_role == OrganizationRole.OWNER:
        return
    owners = [
        membership
        for membership in memberships
        if membership.organization_id == target.organization_id
        and membership.role == OrganizationRole.OWNER
    ]
    if len(owners) <= 1:
        raise ValueError("LAST_OWNER_REQUIRED")


def role_permission_matrix() -> dict[str, tuple[str, ...]]:
    return {
        role.value: tuple(
            permission.value for permission in sorted(permissions, key=str)
        )
        for role, permissions in _ROLE_PERMISSIONS.items()
    }
