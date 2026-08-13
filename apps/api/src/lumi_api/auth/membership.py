from __future__ import annotations

from uuid import UUID

from lumi_auth import Membership, require_last_owner_invariant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import OrganizationMember

from .errors import PermissionDenied

_ALLOWED_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER", "BILLING"}


class MembershipService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _active_memberships(self, organization_id: UUID) -> tuple[OrganizationMember, ...]:
        rows = (
            await self.session.scalars(
                select(OrganizationMember)
                .where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.status == "active",
                )
                .order_by(OrganizationMember.created_at, OrganizationMember.id)
            )
        ).all()
        return tuple(rows)

    @staticmethod
    def _to_policy(rows: tuple[OrganizationMember, ...]) -> tuple[Membership, ...]:
        return tuple(
            Membership(
                user_id=str(row.user_id),
                organization_id=str(row.organization_id),
                role=row.role,  # type: ignore[arg-type]
                active=row.status == "active",
            )
            for row in rows
        )

    @staticmethod
    def _can_manage(actor: OrganizationMember, target: OrganizationMember) -> bool:
        if actor.role == "OWNER":
            return True
        if actor.role == "ADMIN":
            return target.role not in {"OWNER", "ADMIN"}
        return False

    async def change_role(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        target_user_id: UUID,
        new_role: str,
    ) -> OrganizationMember:
        if new_role not in _ALLOWED_ROLES:
            raise ValueError("INVALID_ROLE")
        rows = await self._active_memberships(organization_id)
        actor = next((row for row in rows if row.user_id == actor_id), None)
        target = next((row for row in rows if row.user_id == target_user_id), None)
        if actor is None or target is None or not self._can_manage(actor, target):
            raise PermissionDenied("permission denied")
        if actor.role == "ADMIN" and new_role in {"OWNER", "ADMIN"}:
            raise PermissionDenied("permission denied")

        require_last_owner_invariant(
            self._to_policy(rows),
            organization_id=str(organization_id),
            target_user_id=str(target_user_id),
            target_role_after=new_role,  # type: ignore[arg-type]
        )
        target.role = new_role
        await self.session.flush()
        return target

    async def remove_member(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        target_user_id: UUID,
    ) -> None:
        rows = await self._active_memberships(organization_id)
        actor = next((row for row in rows if row.user_id == actor_id), None)
        target = next((row for row in rows if row.user_id == target_user_id), None)
        if actor is None or target is None or not self._can_manage(actor, target):
            raise PermissionDenied("permission denied")

        require_last_owner_invariant(
            self._to_policy(rows),
            organization_id=str(organization_id),
            target_user_id=str(target_user_id),
            target_role_after=None,
        )
        target.status = "removed"
        await self.session.flush()
