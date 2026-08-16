from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app
from lumi_api.api.v1.auth_dependencies import (
    AuthHttpSettings,
    get_auth_http_settings,
    get_auth_service,
)
from lumi_api.api.v1.dependencies import get_api_v1_service
from lumi_api.api.v1.schemas import ProjectCreateRequest, ProjectResponse
from lumi_api.auth import AuthService, MemoryAuthStore, OrganizationRole, Permission
from lumi_api.domain.ids import new_uuid7
from lumi_api.domain.states import ProjectStatus

NOW = datetime(2026, 8, 16, 7, 15, tzinfo=UTC)


class TestArgon2idHasher:
    def hash(self, password: str) -> str:
        digest = hashlib.sha256(("guard-test:" + password).encode()).hexdigest()
        return f"$argon2id$test-only${digest}"

    def verify(self, encoded_hash: str, password: str) -> bool:
        return encoded_hash == self.hash(password)


class FakeProjectService:
    async def create_project(
        self,
        organization_id: UUID,
        request: ProjectCreateRequest,
        *,
        idempotency_key: str,
    ) -> ProjectResponse:
        return ProjectResponse(
            id=new_uuid7(),
            organization_id=organization_id,
            workspace_id=request.workspace_id,
            name=request.name,
            status=ProjectStatus.DRAFT,
            brief=request.brief,
            brand_id=request.brand_id,
            active_branch_id=None,
            settings=request.settings,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )


def setup_client():
    auth = AuthService(store=MemoryAuthStore(), password_hasher=TestArgon2idHasher())
    app = create_contract_app()
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_auth_http_settings] = lambda: AuthHttpSettings(
        environment="local",
        allowed_origins=frozenset({"http://testserver"}),
    )
    app.dependency_overrides[get_api_v1_service] = lambda: FakeProjectService()
    client = TestClient(app)
    user = auth.register(
        email="owner@example.com",
        display_name="Owner",
        password="correct horse battery staple",
        now=NOW,
    )
    org = new_uuid7()
    auth.add_organization_membership(
        organization_id=org,
        user_id=user.id,
        role=OrganizationRole.OWNER,
        now=NOW,
    )
    grant = auth.login(email=user.email, password="correct horse battery staple", now=NOW)
    principal = auth.principal_for_session(grant.session_secret, organization_id=org, now=NOW)
    return client, auth, org, grant, principal


def project_payload() -> dict[str, object]:
    return {
        "workspace_id": str(new_uuid7()),
        "name": "Secure Project",
        "brief": {"goal": "security"},
        "settings": {},
    }


def test_business_api_requires_authentication() -> None:
    client, _, org, _, _ = setup_client()
    response = client.post(
        "/api/v1/projects",
        headers={
            "X-Organization-ID": str(org),
            "Idempotency-Key": "secure-project-create",
        },
        json=project_payload(),
    )
    assert response.status_code == 401


def test_limited_api_token_cannot_write_business_resource() -> None:
    client, auth, org, _, principal = setup_client()
    issued = auth.create_api_token(
        principal=principal,
        name="read-only",
        scopes=(Permission.PROJECT_READ.value,),
        now=NOW,
    )
    response = client.post(
        "/api/v1/projects",
        headers={
            "Authorization": f"Bearer {issued.secret}",
            "X-Organization-ID": str(org),
            "Idempotency-Key": "secure-project-create",
        },
        json=project_payload(),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_write_scoped_api_token_can_create_project() -> None:
    client, auth, org, _, principal = setup_client()
    issued = auth.create_api_token(
        principal=principal,
        name="writer",
        scopes=(Permission.PROJECT_READ.value, Permission.PROJECT_WRITE.value),
        now=NOW,
    )
    response = client.post(
        "/api/v1/projects",
        headers={
            "Authorization": f"Bearer {issued.secret}",
            "X-Organization-ID": str(org),
            "Idempotency-Key": "secure-project-create",
        },
        json=project_payload(),
    )
    assert response.status_code == 201
    assert response.json()["organization_id"] == str(org)


def test_cross_tenant_header_returns_not_found_category() -> None:
    client, auth, _, _, principal = setup_client()
    issued = auth.create_api_token(
        principal=principal,
        name="writer",
        scopes=(Permission.PROJECT_WRITE.value,),
        now=NOW,
    )
    response = client.post(
        "/api/v1/projects",
        headers={
            "Authorization": f"Bearer {issued.secret}",
            "X-Organization-ID": str(new_uuid7()),
            "Idempotency-Key": "secure-project-create",
        },
        json=project_payload(),
    )
    assert response.status_code in {401, 404}
    assert response.json()["code"] == "tenant_resource_not_found"


def test_cookie_authenticated_write_requires_csrf() -> None:
    client, _, org, grant, _ = setup_client()
    client.cookies.set("lumi_session", grant.session_secret)
    response = client.post(
        "/api/v1/projects",
        headers={
            "X-Organization-ID": str(org),
            "Idempotency-Key": "secure-project-create",
            "Origin": "http://testserver",
        },
        json=project_payload(),
    )
    assert response.status_code == 403
    assert response.json()["code"].startswith("csrf_")
