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
from lumi_api.auth import AuthService, MemoryAuthStore, OrganizationRole, Permission
from lumi_api.projects import MemoryProjectRepository, ProjectCoreService
from lumi_api.projects.api_adapter import ProjectApiAdapter

NOW = datetime(2026, 8, 16, 15, 50, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")


class TestArgon2idHasher:
    def hash(self, password: str) -> str:
        digest = hashlib.sha256(("node17:" + password).encode()).hexdigest()
        return f"$argon2id$test-only${digest}"

    def verify(self, encoded_hash: str, password: str) -> bool:
        return encoded_hash == self.hash(password)


def setup_client() -> tuple[TestClient, str]:
    auth = AuthService(store=MemoryAuthStore(), password_hasher=TestArgon2idHasher())
    user = auth.register(
        email="project-owner@example.com",
        display_name="Project Owner",
        password="correct horse battery staple",
        now=NOW,
    )
    auth.add_organization_membership(
        organization_id=ORG,
        user_id=user.id,
        role=OrganizationRole.OWNER,
        now=NOW,
    )
    session = auth.login(email=user.email, password="correct horse battery staple", now=NOW)
    owner = auth.principal_for_session(session.session_secret, organization_id=ORG, now=NOW)
    issued = auth.create_api_token(
        principal=owner,
        name="node17-project-runtime",
        scopes=(Permission.PROJECT_READ.value, Permission.PROJECT_WRITE.value),
        now=NOW,
    )
    token_principal = auth.authenticate_api_token(issued.secret, now=NOW)

    repo = MemoryProjectRepository()
    repo.register_workspace(ORG, WORKSPACE)
    project_service = ProjectCoreService(repo)
    project_api = ProjectApiAdapter(project_service, principal=token_principal)

    app = create_contract_app()
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_auth_http_settings] = lambda: AuthHttpSettings(
        environment="local",
        allowed_origins=frozenset({"http://testserver"}),
    )
    app.dependency_overrides[get_api_v1_service] = lambda: project_api
    return TestClient(app), issued.secret


def headers(token: str, *, if_match: int | None = None) -> dict[str, str]:
    result = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(ORG),
    }
    if if_match is not None:
        result["If-Match"] = f'W/"{if_match}"'
    return result


def test_authenticated_project_http_lifecycle_and_brief_history() -> None:
    client, token = setup_client()
    create_headers = headers(token)
    create_headers["Idempotency-Key"] = "node17-http-project-create"
    response = client.post(
        "/api/v1/projects",
        headers=create_headers,
        json={
            "workspace_id": str(WORKSPACE),
            "name": "Coffee HTTP Project",
            "brief": {
                "objective": "Launch a premium coffee identity",
                "audience": ["urban professionals"],
                "locale": "zh-CN",
            },
            "settings": {
                "default_locale": "zh-CN",
                "timezone": "Asia/Shanghai",
                "quality_profile": "high",
            },
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    project_id = project["id"]
    assert project["brief_version"] == 1
    assert project["active_branch_id"] is None

    list_response = client.get(
        "/api/v1/projects?status=draft&q=coffee&limit=10",
        headers=headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()["items"]] == [project_id]

    patch_response = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=headers(token, if_match=1),
        json={
            "brief": {
                "objective": "Launch the approved premium coffee identity",
                "audience": ["urban professionals"],
                "locale": "zh-CN",
            },
            "brief_change_reason": "stakeholder approval",
        },
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["brief_version"] == 2

    history = client.get(
        f"/api/v1/projects/{project_id}/brief/versions",
        headers=headers(token),
    )
    assert history.status_code == 200, history.text
    assert [item["version"] for item in history.json()["items"]] == [1, 2]

    archive = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=headers(token, if_match=2),
    )
    assert archive.status_code == 200, archive.text
    assert archive.json()["status"] == "archived"
    assert archive.json()["archived_at"] is not None

    restore = client.post(
        f"/api/v1/projects/{project_id}/restore",
        headers=headers(token, if_match=3),
    )
    assert restore.status_code == 200, restore.text
    assert restore.json()["status"] == "active"
    assert restore.json()["archived_at"] is None
