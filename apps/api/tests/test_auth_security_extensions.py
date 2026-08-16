from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from lumi_api.auth import (
    AuthFlowError,
    AuthService,
    InvalidCredentials,
    MemoryAuthStore,
    OrganizationRole,
)
from lumi_api.domain.ids import new_uuid7

NOW = datetime(2026, 8, 16, 7, 30, tzinfo=UTC)


class TestArgon2idHasher:
    def hash(self, password: str) -> str:
        digest = hashlib.sha256(("extension-test:" + password).encode()).hexdigest()
        return f"$argon2id$test-only${digest}"

    def verify(self, encoded_hash: str, password: str) -> bool:
        return encoded_hash == self.hash(password)


def make_auth() -> AuthService:
    return AuthService(
        store=MemoryAuthStore(),
        password_hasher=TestArgon2idHasher(),
    )


def register(auth: AuthService, email: str = "owner@example.com"):
    return auth.register(
        email=email,
        display_name="Owner",
        password="correct horse battery staple",
        now=NOW,
    )


def owner_principal(auth: AuthService):
    user = register(auth)
    organization_id = new_uuid7()
    auth.add_organization_membership(
        organization_id=organization_id,
        user_id=user.id,
        role=OrganizationRole.OWNER,
        now=NOW,
    )
    grant = auth.login(
        email=user.email,
        password="correct horse battery staple",
        now=NOW,
    )
    principal = auth.principal_for_session(
        grant.session_secret,
        organization_id=organization_id,
        now=NOW,
    )
    return user, organization_id, grant, principal


def test_email_verification_is_hash_only_and_single_use() -> None:
    auth = make_auth()
    user = register(auth)
    issued = auth.create_email_verification(user_id=user.id, now=NOW)
    assert issued.secret not in str(issued.token.model_dump())
    verified = auth.consume_email_verification(
        issued.secret,
        now=NOW + timedelta(minutes=1),
    )
    assert verified.email_verified_at == NOW + timedelta(minutes=1)
    with pytest.raises(AuthFlowError, match="EMAIL_VERIFICATION_INVALID"):
        auth.consume_email_verification(
            issued.secret,
            now=NOW + timedelta(minutes=2),
        )


def test_invite_cannot_attach_a_different_user_id() -> None:
    auth = make_auth()
    _, _, _, principal = owner_principal(auth)
    invite = auth.create_invite(
        principal=principal,
        email="invitee@example.com",
        role=OrganizationRole.EDITOR,
        now=NOW,
    )
    other = auth.register(
        email="other@example.com",
        display_name="Other",
        password="other correct horse password",
        now=NOW,
    )
    with pytest.raises(AuthFlowError, match="INVITE_INVALID"):
        auth.accept_invite(
            invite.secret,
            user_id=other.id,
            email="invitee@example.com",
            now=NOW + timedelta(minutes=1),
        )


def test_revoked_invite_cannot_be_accepted() -> None:
    auth = make_auth()
    _, _, _, principal = owner_principal(auth)
    invite = auth.create_invite(
        principal=principal,
        email="invitee@example.com",
        role=OrganizationRole.EDITOR,
        now=NOW,
    )
    auth.revoke_invite(
        invite.token.id,
        principal=principal,
        now=NOW + timedelta(seconds=1),
    )
    invitee = auth.register(
        email="invitee@example.com",
        display_name="Invitee",
        password="invitee correct horse password",
        now=NOW,
    )
    with pytest.raises(AuthFlowError, match="INVITE_INVALID"):
        auth.accept_invite(
            invite.secret,
            user_id=invitee.id,
            email=invitee.email,
            now=NOW + timedelta(minutes=1),
        )


def test_recent_authentication_expires_independently_of_session() -> None:
    auth = make_auth()
    _, _, grant, _ = owner_principal(auth)
    assert auth.require_recent_authentication(
        grant.session_secret,
        now=NOW + timedelta(minutes=5),
    )
    with pytest.raises(InvalidCredentials, match="RECENT_AUTH_REQUIRED"):
        auth.require_recent_authentication(
            grant.session_secret,
            now=NOW + timedelta(minutes=11),
        )


def test_password_change_revokes_existing_sessions() -> None:
    auth = make_auth()
    user = register(auth)
    grant = auth.login(
        email=user.email,
        password="correct horse battery staple",
        now=NOW,
    )
    auth.change_password(
        user_id=user.id,
        current_password="correct horse battery staple",
        new_password="brand new correct horse password",
        now=NOW + timedelta(minutes=1),
    )
    with pytest.raises(InvalidCredentials, match="SESSION_INVALID"):
        auth.authenticate_session(
            grant.session_secret,
            now=NOW + timedelta(minutes=2),
        )
    new_grant = auth.login(
        email=user.email,
        password="brand new correct horse password",
        now=NOW + timedelta(minutes=3),
    )
    assert new_grant.session.user_id == user.id
