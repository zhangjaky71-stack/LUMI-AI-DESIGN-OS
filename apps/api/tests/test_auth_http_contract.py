from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app
from lumi_api.api.v1.auth_dependencies import (
    AuthHttpSettings,
    get_auth_http_settings,
    get_auth_service,
)
from lumi_api.auth import AuthService, MemoryAuthStore, OrganizationRole
from lumi_api.domain.ids import new_uuid7


class TestArgon2idHasher:
    def hash(self, password: str) -> str:
        digest = hashlib.sha256(("http-test:" + password).encode()).hexdigest()
        return f"$argon2id$test-only${digest}"

    def verify(self, encoded_hash: str, password: str) -> bool:
        return encoded_hash == self.hash(password)


def client_fixture() -> tuple[TestClient, AuthService]:
    auth = AuthService(store=MemoryAuthStore(), password_hasher=TestArgon2idHasher())
    app = create_contract_app()
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_auth_http_settings] = lambda: AuthHttpSettings(
        environment="local",
        allowed_origins=frozenset({"http://testserver"}),
    )
    return TestClient(app), auth


def test_http_register_login_me_logout_flow() -> None:
    client, auth = client_fixture()
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
    )
    assert register.status_code == 201
    user_id = register.json()["id"]
    organization_id = new_uuid7()
    auth.add_organization_membership(
        organization_id=organization_id,
        user_id=next(iter(auth.store.users)),
        role=OrganizationRole.OWNER,
        now=datetime.now(UTC),
    )

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert login.status_code == 200
    assert login.json()["user_id"] == user_id
    set_cookie = login.headers.get_list("set-cookie")
    session_cookie = next(value for value in set_cookie if value.startswith("lumi_session="))
    csrf_cookie = next(value for value in set_cookie if value.startswith("lumi_csrf="))
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in session_cookie
    assert "Secure" not in session_cookie

    me = client.get(
        "/api/v1/auth/me",
        headers={"X-Organization-ID": str(organization_id)},
    )
    assert me.status_code == 200
    assert me.json()["organization_id"] == str(organization_id)
    assert "OWNER" in me.json()["roles"]

    missing_csrf = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )
    assert missing_csrf.status_code == 403

    csrf = client.cookies.get("lumi_csrf")
    assert csrf
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 200
    assert logout.json() == {"logged_out": True}


def test_http_login_does_not_reveal_account_existence() -> None:
    client, _ = client_fixture()
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
    )
    missing = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong password here"},
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong password here"},
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["code"] == wrong.json()["code"] == "invalid_credentials"
    assert missing.json()["detail"] == wrong.json()["detail"]


def test_openapi_exposes_auth_contract_without_password_in_responses() -> None:
    client, _ = client_fixture()
    schema = client.get("/api/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/me" in paths
    assert "password" not in str(paths["/api/v1/auth/login"]["post"]["responses"])
