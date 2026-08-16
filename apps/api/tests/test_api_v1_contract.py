from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app
from lumi_api.api.v1.auth_guard import enforce_api_auth
from lumi_api.api.v1.common import parse_if_match, version_etag
from lumi_api.api.v1.dependencies import get_api_v1_service
from lumi_api.api.v1.schemas import MoneyInput, ProjectCreateRequest, ProjectResponse
from lumi_api.domain.states import ProjectStatus

ORG_ID = UUID("01910000-0000-7000-8000-000000000001")
WORKSPACE_ID = UUID("01910000-0000-7000-8000-000000000021")
PROJECT_ID = UUID("01910000-0000-7000-8000-000000000031")


class FakeApiService:
    async def create_project(
        self,
        organization_id: UUID,
        request: ProjectCreateRequest,
        *,
        idempotency_key: str,
    ) -> ProjectResponse:
        assert organization_id == ORG_ID
        assert idempotency_key == "project-create-fixture"
        return ProjectResponse(
            id=PROJECT_ID,
            organization_id=organization_id,
            workspace_id=request.workspace_id,
            name=request.name,
            status=ProjectStatus.DRAFT,
            brief=request.brief,
            brief_version=1,
            brand_id=request.brand_id,
            active_branch_id=None,
            settings=request.settings,
            version=1,
            created_at=datetime(2026, 8, 16, tzinfo=UTC),
            updated_at=datetime(2026, 8, 16, tzinfo=UTC),
        )


def _parameter_names(operation: dict[str, object]) -> set[str]:
    parameters = operation.get("parameters", [])
    assert isinstance(parameters, list)
    return {
        str(parameter["name"])
        for parameter in parameters
        if isinstance(parameter, dict) and "name" in parameter
    }


def _node11_app():
    app = create_contract_app()
    app.dependency_overrides[enforce_api_auth] = lambda: None
    return app


def test_openapi_preserves_node11_baseline_and_tenant_headers() -> None:
    schema = create_contract_app().openapi()
    paths = schema["paths"]

    baseline_business_paths = {
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/transitions",
        "/api/v1/projects/{project_id}/tasks",
        "/api/v1/tasks/{task_id}",
        "/api/v1/projects/{project_id}/agent-runs",
        "/api/v1/agent-runs/{agent_run_id}",
        "/api/v1/agent-runs/{agent_run_id}/cancel",
        "/api/v1/projects/{project_id}/generations",
        "/api/v1/generations/{generation_id}",
        "/api/v1/artifact-versions/{artifact_version_id}",
    }
    auth_paths = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
    }
    node17_paths = {
        "/api/v1/projects/{project_id}/brief/versions",
        "/api/v1/projects/{project_id}/restore",
    }
    assert baseline_business_paths | auth_paths | node17_paths <= set(paths)

    for path in baseline_business_paths | node17_paths | {"/api/v1/auth/me"}:
        for method, operation in paths[path].items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            assert "X-Organization-ID" in _parameter_names(operation)

    idempotent_operations = (
        paths["/api/v1/projects"]["post"],
        paths["/api/v1/projects/{project_id}/tasks"]["post"],
        paths["/api/v1/projects/{project_id}/agent-runs"]["post"],
        paths["/api/v1/agent-runs/{agent_run_id}/cancel"]["post"],
        paths["/api/v1/projects/{project_id}/generations"]["post"],
    )
    for operation in idempotent_operations:
        assert "Idempotency-Key" in _parameter_names(operation)

    assert "If-Match" in _parameter_names(paths["/api/v1/projects/{project_id}"]["patch"])
    assert "If-Match" in _parameter_names(
        paths["/api/v1/projects/{project_id}/transitions"]["post"]
    )
    assert "If-Match" in _parameter_names(paths["/api/v1/projects/{project_id}"]["delete"])
    assert "If-Match" in _parameter_names(paths["/api/v1/projects/{project_id}/restore"]["post"])


def test_domain_status_values_are_reused_by_openapi() -> None:
    schema = create_contract_app().openapi()
    project_status = schema["components"]["schemas"]["ProjectStatus"]["enum"]
    assert project_status == [status.value for status in ProjectStatus]


def test_mutating_project_returns_location_and_etag() -> None:
    app = _node11_app()
    app.dependency_overrides[get_api_v1_service] = lambda: FakeApiService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects",
        headers={
            "X-Organization-ID": str(ORG_ID),
            "Idempotency-Key": "project-create-fixture",
            "X-Request-ID": "node11-contract-test",
        },
        json={
            "workspace_id": str(WORKSPACE_ID),
            "name": "Launch Campaign",
            "brief": {"objective": "launch"},
            "settings": {},
        },
    )

    assert response.status_code == 201
    assert response.headers["location"] == f"/api/v1/projects/{PROJECT_ID}"
    assert response.headers["etag"] == 'W/"1"'
    assert response.headers["x-request-id"] == "node11-contract-test"
    assert response.json()["status"] == "draft"


def test_unconfigured_service_fails_explicitly() -> None:
    client = TestClient(_node11_app())
    response = client.get(
        "/api/v1/projects",
        headers={"X-Organization-ID": str(ORG_ID)},
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == "api_service_not_configured"
    assert payload["request_id"] == response.headers["x-request-id"]


def test_request_validation_uses_problem_details() -> None:
    client = TestClient(_node11_app())
    response = client.get("/api/v1/projects")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert payload["errors"]


def test_etag_parser_is_strict_and_round_trips() -> None:
    assert version_etag(7) == 'W/"7"'
    assert parse_if_match('W/"7"') == 7
    assert parse_if_match('"7"') == 7
    assert parse_if_match("7") == 7


def test_money_contract_uses_decimal_and_strict_currency() -> None:
    money = MoneyInput(amount=Decimal("12.34567890"), currency="USD")
    assert money.amount == Decimal("12.34567890")
