from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import pytest
from lumi_domain import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.auth.errors import PermissionDenied
from lumi_api.auth.secure_service import SecureAuthService
from lumi_api.auth.service import AuthService
from lumi_api.persistence.models import OrganizationMember
from lumi_api.persistence.session import create_engine

if os.environ.get("LUMI_AUTH_INTEGRATION") != "1":
    pytest.skip("set LUMI_AUTH_INTEGRATION=1 to run auth PostgreSQL tests", allow_module_level=True)

T = TypeVar("T")
NOW = datetime(2026, 8, 13, 4, 0, tzinfo=UTC)


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


async def _admin_invite_role_ceiling() -> None:
    engine = create_engine()
    suffix = str(new_uuid7())[-12:]
    password = "secure integration password 123"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                bootstrap = AuthService(session)
                owner = await bootstrap.register_local(
                    email=f"owner-{suffix}@example.test",
                    password=password,
                    display_name="Owner",
                    organization_name="Role Ceiling Org",
                    organization_slug=f"role-ceiling-{suffix}",
                    client_key=f"owner-{suffix}",
                    now=NOW,
                )
                admin = await bootstrap.register_local(
                    email=f"admin-{suffix}@example.test",
                    password=password,
                    display_name="Admin",
                    organization_name="Admin Temp Org",
                    organization_slug=f"admin-temp-{suffix}",
                    client_key=f"admin-{suffix}",
                    now=NOW,
                )
                session.add(
                    OrganizationMember(
                        id=new_uuid7(),
                        organization_id=owner.organization_id,
                        user_id=admin.user_id,
                        role="ADMIN",
                        status="active",
                    )
                )
                await session.flush()

                secure = SecureAuthService(session)
                for forbidden_role in ("OWNER", "ADMIN"):
                    with pytest.raises(PermissionDenied):
                        await secure.create_invite(
                            actor_id=admin.user_id,
                            organization_id=owner.organization_id,
                            email=f"target-{forbidden_role.lower()}-{suffix}@example.test",
                            role=forbidden_role,
                            client_key=f"invite-{suffix}-{forbidden_role}",
                            now=NOW + timedelta(minutes=1),
                        )

                token = await secure.create_invite(
                    actor_id=admin.user_id,
                    organization_id=owner.organization_id,
                    email=f"editor-target-{suffix}@example.test",
                    role="EDITOR",
                    client_key=f"invite-editor-{suffix}",
                    now=NOW + timedelta(minutes=2),
                )
                assert token.startswith("lumi_invite_")

                admin_membership = await session.scalar(
                    select(OrganizationMember).where(
                        OrganizationMember.organization_id == owner.organization_id,
                        OrganizationMember.user_id == admin.user_id,
                    )
                )
                assert admin_membership is not None and admin_membership.role == "ADMIN"
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_admin_cannot_invite_owner_or_admin() -> None:
    run(_admin_invite_role_ceiling())
