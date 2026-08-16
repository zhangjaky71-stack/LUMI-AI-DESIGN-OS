from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_api.auth import (
    AccessPolicyService,
    AuthFlowError,
    AuthService,
    HttpAuthInput,
    InvalidCredentials,
    MemoryAuthStore,
    OrganizationRole,
    Permission,
    SessionCookiePolicy,
    TenantAccessDenied,
    WorkspaceRole,
    authenticate_http_request,
    build_request_context,
    hash_secret,
    require_tenant_resource,
    role_permission_matrix,
    validate_csrf,
)
from lumi_api.domain.ids import new_uuid7

NOW = datetime(2026, 8, 16, 7, 0, tzinfo=UTC)


@dataclass
class TestArgon2idHasher:
    verify_calls: int = 0

    def hash(self, password: str) -> str:
        digest = hashlib.sha256(("test-only:" + password).encode()).hexdigest()
        return f"$argon2id$test-only${digest}"

    def verify(self, encoded_hash: str, password: str) -> bool:
        self.verify_calls += 1
        return encoded_hash == self.hash(password)


def service() -> tuple[AuthService, MemoryAuthStore, TestArgon2idHasher]:
    store = MemoryAuthStore()
    hasher = TestArgon2idHasher()
    return AuthService(store=store, password_hasher=hasher), store, hasher


def registered(auth: AuthService, email: str = "owner@example.com"):
    return auth.register(
        email=email,
        display_name="Owner",
        password="correct horse battery staple",
        now=NOW,
    )


def owner_session(auth: AuthService, organization_id: UUID):
    user = registered(auth)
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
    return user, grant, principal


def test_register_hashes_password_with_argon2id_contract() -> None:
    auth, store, _ = service()
    user = registered(auth)
    credential = store.credentials[user.id]
    assert credential.algorithm == "argon2id"
    assert credential.password_hash.startswith("$argon2id$")
    assert "correct horse battery staple" not in credential.password_hash


def test_unknown_and_wrong_password_share_generic_login_failure() -> None:
    auth, _, hasher = service()
    registered(auth)
    with pytest.raises(InvalidCredentials, match="INVALID_CREDENTIALS"):
        auth.login(email="missing@example.com", password="wrong password here", now=NOW)
    unknown_calls = hasher.verify_calls
    with pytest.raises(InvalidCredentials, match="INVALID_CREDENTIALS"):
        auth.login(email="owner@example.com", password="wrong password here", now=NOW)
    assert hasher.verify_calls == unknown_calls + 1


def test_session_secret_is_not_stored_in_plaintext_and_logout_revokes() -> None:
    auth, store, _ = service()
    registered(auth)
    grant = auth.login(
        email="owner@example.com",
        password="correct horse battery staple",
        now=NOW,
    )
    assert grant.session.id == hash_secret(grant.session_secret)
    assert grant.session_secret not in store.sessions
    assert auth.authenticate_session(grant.session_secret, now=NOW).is_active(NOW)
    auth.logout(grant.session_secret, now=NOW + timedelta(seconds=1))
    with pytest.raises(InvalidCredentials, match="SESSION_INVALID"):
        auth.authenticate_session(grant.session_secret, now=NOW + timedelta(seconds=2))


def test_session_expiry_fails_closed() -> None:
    auth, _, _ = service()
    registered(auth)
    grant = auth.login(
        email="owner@example.com",
        password="correct horse battery staple",
        now=NOW,
    )
    with pytest.raises(InvalidCredentials, match="SESSION_INVALID"):
        auth.authenticate_session(grant.session_secret, now=NOW + timedelta(days=15))


def test_csrf_requires_origin_cookie_and_matching_header() -> None:
    allowed = frozenset({"https://app.lumi.example"})
    validate_csrf(
        method="GET",
        origin=None,
        allowed_origins=allowed,
        csrf_cookie=None,
        csrf_header=None,
    )
    with pytest.raises(ValueError, match="CSRF_ORIGIN_REQUIRED"):
        validate_csrf(
            method="POST",
            origin=None,
            allowed_origins=allowed,
            csrf_cookie="a",
            csrf_header="a",
        )
    with pytest.raises(ValueError, match="CSRF_ORIGIN_DENIED"):
        validate_csrf(
            method="POST",
            origin="https://evil.example",
            allowed_origins=allowed,
            csrf_cookie="a",
            csrf_header="a",
        )
    with pytest.raises(ValueError, match="CSRF_TOKEN_MISMATCH"):
        validate_csrf(
            method="POST",
            origin="https://app.lumi.example/path",
            allowed_origins=allowed,
            csrf_cookie="a",
            csrf_header="b",
        )


def test_cookie_policy_is_secure_except_local_development() -> None:
    assert SessionCookiePolicy.for_environment("production").secure is True
    assert SessionCookiePolicy.for_environment("local").secure is False
    policy = SessionCookiePolicy.for_environment("production")
    assert policy.httponly is True
    assert policy.path == "/"
    assert policy.samesite == "lax"


def test_role_permission_matrix_is_frozen() -> None:
    matrix = role_permission_matrix()
    assert Permission.PROJECT_READ.value in matrix[OrganizationRole.VIEWER.value]
    assert Permission.PROJECT_WRITE.value not in matrix[OrganizationRole.VIEWER.value]
    assert Permission.BILLING_MANAGE.value in matrix[OrganizationRole.BILLING.value]
    assert Permission.PROJECT_WRITE.value not in matrix[OrganizationRole.BILLING.value]
    assert Permission.MEMBER_MANAGE.value in matrix[OrganizationRole.OWNER.value]
    assert Permission.BILLING_MANAGE.value not in matrix[OrganizationRole.ADMIN.value]


def test_cross_tenant_session_selection_is_not_enumerable() -> None:
    auth, _, _ = service()
    org_a = new_uuid7()
    org_b = new_uuid7()
    _, grant, _ = owner_session(auth, org_a)
    with pytest.raises(InvalidCredentials, match="TENANT_RESOURCE_NOT_FOUND"):
        auth.principal_for_session(
            grant.session_secret,
            organization_id=org_b,
            now=NOW,
        )


def test_request_context_carries_actor_tenant_roles_and_permissions() -> None:
    auth, _, _ = service()
    org = new_uuid7()
    _, _, principal = owner_session(auth, org)
    workspace = new_uuid7()
    context = build_request_context(
        principal=principal,
        request_id="req-1",
        trace_id="trace-1",
        organization_id=org,
        workspace_id=workspace,
    )
    assert context.organization_id == org
    assert context.workspace_id == workspace
    assert Permission.PROJECT_WRITE.value in context.permissions


def test_last_owner_cannot_be_demoted() -> None:
    auth, store, _ = service()
    org = new_uuid7()
    user = registered(auth)
    membership = auth.add_organization_membership(
        organization_id=org,
        user_id=user.id,
        role=OrganizationRole.OWNER,
        now=NOW,
    )
    with pytest.raises(ValueError, match="LAST_OWNER_REQUIRED"):
        auth.change_membership_role(
            membership.id,
            new_role=OrganizationRole.ADMIN,
            actor_id=str(user.id),
            now=NOW,
        )
    assert store.organization_memberships[membership.id].role == OrganizationRole.OWNER


def test_workspace_membership_requires_organization_membership() -> None:
    auth, _, _ = service()
    user = registered(auth)
    with pytest.raises(AuthFlowError, match="ORGANIZATION_MEMBERSHIP_REQUIRED"):
        auth.add_workspace_membership(
            organization_id=new_uuid7(),
            workspace_id=new_uuid7(),
            user_id=user.id,
            role=WorkspaceRole.EDITOR,
            now=NOW,
        )


def test_invite_is_hash_only_and_replay_is_rejected() -> None:
    auth, store, _ = service()
    org = new_uuid7()
    _, _, principal = owner_session(auth, org)
    invite = auth.create_invite(
        principal=principal,
        email="new@example.com",
        role=OrganizationRole.EDITOR,
        now=NOW,
    )
    assert invite.secret not in str(invite.token.model_dump())
    invitee = auth.register(
        email="new@example.com",
        display_name="New",
        password="another correct horse password",
        now=NOW,
    )
    membership = auth.accept_invite(
        invite.secret,
        user_id=invitee.id,
        email=invitee.email,
        now=NOW + timedelta(minutes=1),
    )
    assert membership.organization_id == org
    with pytest.raises(AuthFlowError, match="INVITE_INVALID"):
        auth.accept_invite(
            invite.secret,
            user_id=invitee.id,
            email=invitee.email,
            now=NOW + timedelta(minutes=2),
        )
    assert hash_secret(invite.secret) in store.one_time_tokens


def test_password_reset_is_single_use_and_revokes_sessions() -> None:
    auth, _, _ = service()
    user = registered(auth)
    grant = auth.login(
        email=user.email,
        password="correct horse battery staple",
        now=NOW,
    )
    reset = auth.create_password_reset(email=user.email, now=NOW)
    assert reset is not None
    auth.consume_password_reset(
        reset.secret,
        new_password="brand new correct horse password",
        now=NOW + timedelta(minutes=1),
    )
    with pytest.raises(InvalidCredentials, match="SESSION_INVALID"):
        auth.authenticate_session(grant.session_secret, now=NOW + timedelta(minutes=2))
    with pytest.raises(AuthFlowError, match="RESET_INVALID"):
        auth.consume_password_reset(
            reset.secret,
            new_password="another brand new password",
            now=NOW + timedelta(minutes=3),
        )


def test_password_reset_unknown_email_does_not_create_token() -> None:
    auth, store, _ = service()
    result = auth.create_password_reset(email="missing@example.com", now=NOW)
    assert result is None
    assert not store.one_time_tokens


def test_api_token_cannot_escalate_scopes_and_authenticates_tenant() -> None:
    auth, _, _ = service()
    org = new_uuid7()
    _, _, principal = owner_session(auth, org)
    with pytest.raises(AuthFlowError, match="TOKEN_SCOPE_ESCALATION"):
        auth.create_api_token(
            principal=principal,
            name="bad",
            scopes=("root.superuser",),
            now=NOW,
        )
    issued = auth.create_api_token(
        principal=principal,
        name="automation",
        scopes=(Permission.PROJECT_READ.value,),
        now=NOW,
    )
    token_principal = auth.authenticate_api_token(issued.secret, now=NOW)
    assert token_principal.organization_id == org
    assert token_principal.permissions == (Permission.PROJECT_READ.value,)
    assert issued.secret not in str(issued.token.model_dump())


def test_http_boundary_requires_csrf_for_cookie_but_not_bearer() -> None:
    auth, _, _ = service()
    org = new_uuid7()
    _, grant, principal = owner_session(auth, org)
    with pytest.raises(ValueError, match="CSRF_TOKEN_REQUIRED"):
        authenticate_http_request(
            HttpAuthInput(
                method="POST",
                organization_id=org,
                origin="https://app.lumi.example",
                authorization=None,
                session_cookie=grant.session_secret,
                csrf_cookie=None,
                csrf_header=None,
            ),
            auth_service=auth,
            now=NOW,
            allowed_origins=frozenset({"https://app.lumi.example"}),
        )
    issued = auth.create_api_token(
        principal=principal,
        name="automation",
        scopes=(Permission.PROJECT_READ.value,),
        now=NOW,
    )
    resolved = authenticate_http_request(
        HttpAuthInput(
            method="POST",
            organization_id=org,
            origin=None,
            authorization=f"Bearer {issued.secret}",
            session_cookie=None,
            csrf_cookie=None,
            csrf_header=None,
        ),
        auth_service=auth,
        now=NOW,
        allowed_origins=frozenset({"https://app.lumi.example"}),
    )
    assert resolved.actor_type.value == "API_TOKEN"


def test_tenant_guard_returns_same_not_found_category() -> None:
    @dataclass(frozen=True)
    class Resource:
        organization_id: UUID

    org = new_uuid7()
    with pytest.raises(TenantAccessDenied, match="TENANT_RESOURCE_NOT_FOUND"):
        require_tenant_resource(org, None)
    with pytest.raises(TenantAccessDenied, match="TENANT_RESOURCE_NOT_FOUND"):
        require_tenant_resource(org, Resource(new_uuid7()))
    assert require_tenant_resource(org, Resource(org)).organization_id == org


def test_auth_audit_never_contains_plain_password_or_api_token_secret() -> None:
    auth, store, _ = service()
    org = new_uuid7()
    _, _, principal = owner_session(auth, org)
    issued = auth.create_api_token(
        principal=principal,
        name="audit-test",
        scopes=(Permission.PROJECT_READ.value,),
        now=NOW,
    )
    dump = repr([event.model_dump() for event in store.audit_events])
    assert "correct horse battery staple" not in dump
    assert issued.secret not in dump


def test_access_policy_denies_cross_tenant_before_permission_check() -> None:
    auth, _, _ = service()
    org = new_uuid7()
    _, _, principal = owner_session(auth, org)
    decision = AccessPolicyService().authorize(
        principal,
        organization_id=new_uuid7(),
        permission=Permission.PROJECT_READ,
    )
    assert decision.allowed is False
    assert decision.reason_code == "TENANT_RESOURCE_NOT_FOUND"
