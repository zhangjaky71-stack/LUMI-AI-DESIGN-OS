from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar
from uuid import UUID

import pytest
from lumi_auth import hash_token
from lumi_domain import new_uuid7
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.auth.errors import InvalidCredentials, PermissionDenied, SessionInvalid, TokenInvalid
from lumi_api.auth.membership import MembershipService
from lumi_api.auth.principal import PrincipalResolver
from lumi_api.auth.service import AuthService
from lumi_api.persistence.models import (
    ApiToken,
    EmailVerificationToken,
    OrganizationMember,
    PasswordCredential,
    PasswordResetToken,
    Session,
    User,
)
from lumi_api.persistence.session import create_engine

if os.environ.get("LUMI_AUTH_INTEGRATION") != "1":
    pytest.skip("set LUMI_AUTH_INTEGRATION=1 to run auth PostgreSQL tests", allow_module_level=True)

T = TypeVar("T")
NOW = datetime(2026, 8, 13, 3, 30, tzinfo=UTC)


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


async def _head_is_auth_role_hardening() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            head = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            assert head == "0005_auth_role_hardening"
    finally:
        await engine.dispose()


def test_database_is_at_auth_head() -> None:
    run(_head_is_auth_role_hardening())


async def _local_registration_login_logout_reset() -> None:
    engine = create_engine()
    suffix = str(new_uuid7())[-12:]
    email = f"auth-{suffix}@example.test"
    password = "correct horse battery staple 123"
    changed_password = "new correct horse battery staple 456"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                service = AuthService(session)
                registration = await service.register_local(
                    email=email,
                    password=password,
                    display_name="Auth Test",
                    organization_name="Auth Test Org",
                    organization_slug=f"auth-test-{suffix}",
                    client_key=f"test-{suffix}",
                    request_id=f"req-{suffix}",
                    now=NOW,
                )
                credential = await session.scalar(
                    select(PasswordCredential).where(PasswordCredential.user_id == registration.user_id)
                )
                assert credential is not None
                assert credential.password_hash.startswith("$argon2id$")
                assert password not in credential.password_hash

                verification_row = await session.scalar(
                    select(EmailVerificationToken).where(
                        EmailVerificationToken.user_id == registration.user_id
                    )
                )
                assert verification_row is not None
                assert verification_row.token_hash == hash_token(registration.email_verification_token)
                assert registration.email_verification_token not in verification_row.token_hash

                verified_user_id = await service.verify_email(
                    registration.email_verification_token,
                    now=NOW + timedelta(minutes=1),
                )
                assert verified_user_id == registration.user_id
                user = await session.get(User, registration.user_id)
                assert user is not None and user.email_verified_at is not None
                with pytest.raises(TokenInvalid):
                    await service.verify_email(
                        registration.email_verification_token,
                        now=NOW + timedelta(minutes=2),
                    )

                login = await service.login_local(
                    email=email,
                    password=password,
                    client_key=f"login-{suffix}",
                    requested_organization_id=registration.organization_id,
                    user_agent="pytest-auth-agent",
                    request_id=f"login-{suffix}",
                    now=NOW + timedelta(minutes=3),
                )
                session_row = await session.scalar(
                    select(Session).where(Session.user_id == registration.user_id)
                )
                assert session_row is not None
                assert session_row.token_hash == hash_token(login.session_token)
                assert session_row.csrf_token_hash == hash_token(login.csrf_token)
                assert login.session_token not in session_row.token_hash

                with pytest.raises(InvalidCredentials):
                    await service.login_local(
                        email=email,
                        password="definitely wrong",
                        client_key=f"wrong-{suffix}",
                        now=NOW + timedelta(minutes=4),
                    )
                with pytest.raises(InvalidCredentials):
                    await service.login_local(
                        email=f"missing-{suffix}@example.test",
                        password="definitely wrong",
                        client_key=f"missing-{suffix}",
                        now=NOW + timedelta(minutes=4),
                    )

                with pytest.raises(SessionInvalid):
                    await service.logout(
                        session_token=login.session_token,
                        csrf_token="wrong-csrf",
                        origin="https://app.lumi.dev",
                        allowed_origins=frozenset({"https://app.lumi.dev"}),
                        now=NOW + timedelta(minutes=5),
                    )
                await service.logout(
                    session_token=login.session_token,
                    csrf_token=login.csrf_token,
                    origin="https://app.lumi.dev",
                    allowed_origins=frozenset({"https://app.lumi.dev"}),
                    now=NOW + timedelta(minutes=5),
                )
                assert session_row.revoked_at is not None

                login2 = await service.login_local(
                    email=email,
                    password=password,
                    client_key=f"login2-{suffix}",
                    requested_organization_id=registration.organization_id,
                    now=NOW + timedelta(minutes=6),
                )
                reset_plaintext = await service.request_password_reset(
                    email=email,
                    client_key=f"reset-{suffix}",
                    now=NOW + timedelta(minutes=7),
                )
                assert reset_plaintext is not None
                reset_row = await session.scalar(
                    select(PasswordResetToken).where(
                        PasswordResetToken.user_id == registration.user_id
                    ).order_by(PasswordResetToken.created_at.desc())
                )
                assert reset_row is not None
                assert reset_row.token_hash == hash_token(reset_plaintext)

                reset_user_id = await service.reset_password(
                    plaintext_token=reset_plaintext,
                    new_password=changed_password,
                    now=NOW + timedelta(minutes=8),
                )
                assert reset_user_id == registration.user_id
                sessions = (
                    await session.scalars(select(Session).where(Session.user_id == registration.user_id))
                ).all()
                assert sessions and all(item.revoked_at is not None for item in sessions)
                with pytest.raises(TokenInvalid):
                    await service.reset_password(
                        plaintext_token=reset_plaintext,
                        new_password="another strong password 789",
                        now=NOW + timedelta(minutes=9),
                    )
                with pytest.raises(InvalidCredentials):
                    await service.login_local(
                        email=email,
                        password=password,
                        client_key=f"old-password-{suffix}",
                        now=NOW + timedelta(minutes=10),
                    )
                login3 = await service.login_local(
                    email=email,
                    password=changed_password,
                    client_key=f"new-password-{suffix}",
                    requested_organization_id=registration.organization_id,
                    now=NOW + timedelta(minutes=10),
                )
                principal = await PrincipalResolver(session).from_session(
                    plaintext_session_token=login3.session_token,
                    request_id=f"principal-{suffix}",
                    trace_id=f"trace-{suffix}",
                    now=NOW + timedelta(minutes=11),
                )
                assert principal.context.organization_id == str(registration.organization_id)
                assert "project.write" in principal.context.permissions
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_local_registration_login_logout_and_reset_lifecycle() -> None:
    run(_local_registration_login_logout_reset())


async def _invite_api_token_and_owner_invariants() -> None:
    engine = create_engine()
    suffix = str(new_uuid7())[-12:]
    owner_email = f"owner-{suffix}@example.test"
    editor_email = f"editor-{suffix}@example.test"
    password = "integration test secure password 123"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                service = AuthService(session)
                owner = await service.register_local(
                    email=owner_email,
                    password=password,
                    display_name="Owner",
                    organization_name="Invite Org",
                    organization_slug=f"invite-org-{suffix}",
                    client_key=f"owner-{suffix}",
                    now=NOW,
                )
                editor = await service.register_local(
                    email=editor_email,
                    password=password,
                    display_name="Editor",
                    organization_name="Editor Temp Org",
                    organization_slug=f"editor-temp-{suffix}",
                    client_key=f"editor-{suffix}",
                    now=NOW,
                )

                invite_plaintext = await service.create_invite(
                    actor_id=owner.user_id,
                    organization_id=owner.organization_id,
                    email=editor_email,
                    role="EDITOR",
                    client_key=f"invite-{suffix}",
                    now=NOW + timedelta(minutes=1),
                )
                invite_org = await service.accept_invite(
                    actor_id=editor.user_id,
                    plaintext_token=invite_plaintext,
                    now=NOW + timedelta(minutes=2),
                )
                assert invite_org == owner.organization_id
                editor_membership = await session.scalar(
                    select(OrganizationMember).where(
                        OrganizationMember.organization_id == owner.organization_id,
                        OrganizationMember.user_id == editor.user_id,
                    )
                )
                assert editor_membership is not None and editor_membership.role == "EDITOR"
                with pytest.raises(TokenInvalid):
                    await service.accept_invite(
                        actor_id=editor.user_id,
                        plaintext_token=invite_plaintext,
                        now=NOW + timedelta(minutes=3),
                    )

                api_result = await service.create_api_token(
                    actor_id=owner.user_id,
                    organization_id=owner.organization_id,
                    name="CI automation",
                    scopes=frozenset({"projects:read"}),
                    expires_at=NOW + timedelta(days=30),
                )
                api_row = await session.get(ApiToken, api_result.token_id)
                assert api_row is not None
                assert api_row.prefix == api_result.prefix
                assert api_row.secret_hash == hash_token(api_result.plaintext)
                assert api_result.plaintext not in api_row.secret_hash

                api_principal = await PrincipalResolver(session).from_api_token(
                    plaintext_token=api_result.plaintext,
                    required_scope="projects:read",
                    now=NOW + timedelta(minutes=4),
                )
                assert api_principal.organization_id == owner.organization_id
                with pytest.raises(PermissionDenied):
                    await PrincipalResolver(session).from_api_token(
                        plaintext_token=api_result.plaintext,
                        required_scope="projects:write",
                        now=NOW + timedelta(minutes=4),
                    )
                await PrincipalResolver(session).revoke_api_token(
                    actor_id=owner.user_id,
                    organization_id=owner.organization_id,
                    token_id=api_result.token_id,
                    now=NOW + timedelta(minutes=5),
                )
                with pytest.raises(PermissionDenied):
                    await PrincipalResolver(session).from_api_token(
                        plaintext_token=api_result.plaintext,
                        required_scope="projects:read",
                        now=NOW + timedelta(minutes=6),
                    )

                memberships = MembershipService(session)
                with pytest.raises(ValueError, match="LAST_OWNER_REQUIRED"):
                    await memberships.change_role(
                        organization_id=owner.organization_id,
                        actor_id=owner.user_id,
                        target_user_id=owner.user_id,
                        new_role="ADMIN",
                    )
                with pytest.raises(ValueError, match="LAST_OWNER_REQUIRED"):
                    await memberships.remove_member(
                        organization_id=owner.organization_id,
                        actor_id=owner.user_id,
                        target_user_id=owner.user_id,
                    )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_invite_api_token_and_last_owner_invariants() -> None:
    run(_invite_api_token_and_owner_invariants())
