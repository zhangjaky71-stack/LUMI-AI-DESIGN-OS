from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lumi_api.api import create_contract_app

EXPECTED_OPERATION_IDS = {
    "getApiV1Health",
    "listProjects",
    "createProject",
    "getProject",
    "updateProject",
    "archiveProject",
    "listAssets",
    "createAsset",
    "getAsset",
    "getArtifact",
    "listArtifactVersions",
    "createArtifactVersion",
    "createAgentRun",
    "getAgentRun",
    "cancelAgentRun",
    "resumeAgentRun",
    "getTask",
    "createGeneration",
    "getGeneration",
    "decideApproval",
}


def _parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    parameters = operation.get("parameters", [])
    assert isinstance(parameters, list)
    return {
        str(parameter["name"]): parameter
        for parameter in parameters
        if isinstance(parameter, dict) and "name" in parameter
    }


def test_openapi_v1_has_stable_unique_operation_ids() -> None:
    schema = create_contract_app().openapi()
    assert str(schema["openapi"]).startswith("3.1")

    operations: list[str] = []
    for path, path_item in schema["paths"].items():
        assert path.startswith("/api/v1/"), path
        for method, operation in path_item.items():
            if method not in {"get", "post", "patch", "delete", "put"}:
                continue
            operation_id = operation.get("operationId")
            assert isinstance(operation_id, str)
            operations.append(operation_id)

    assert set(operations) == EXPECTED_OPERATION_IDS
    assert len(operations) == len(set(operations))


def test_tenant_header_is_required_on_business_routes_but_not_health() -> None:
    schema = create_contract_app().openapi()
    health_parameters = _parameters(schema["paths"]["/api/v1/health"]["get"])
    assert "X-Lumi-Organization-Id" not in health_parameters

    project_parameters = _parameters(schema["paths"]["/api/v1/projects"]["get"])
    tenant = project_parameters["X-Lumi-Organization-Id"]
    assert tenant["required"] is True


def test_side_effect_and_concurrency_headers_are_contractual() -> None:
    schema = create_contract_app().openapi()

    create_parameters = _parameters(schema["paths"]["/api/v1/projects"]["post"])
    assert create_parameters["Idempotency-Key"]["required"] is False
    assert "X-Lumi-Organization-Id" in create_parameters

    patch_parameters = _parameters(schema["paths"]["/api/v1/projects/{project_id}"]["patch"])
    assert patch_parameters["If-Match"]["required"] is False
    assert "X-Lumi-Organization-Id" in patch_parameters

    approval_parameters = _parameters(schema["paths"]["/api/v1/approvals/{approval_id}:decide"]["post"])
    assert "Idempotency-Key" in approval_parameters
    assert "If-Match" in approval_parameters


def test_cursor_pagination_limit_is_bounded() -> None:
    schema = create_contract_app().openapi()
    parameters = _parameters(schema["paths"]["/api/v1/projects"]["get"])
    limit_schema = parameters["limit"]["schema"]
    assert limit_schema["minimum"] == 1
    assert limit_schema["maximum"] == 100
    assert limit_schema["default"] == 50


def test_problem_details_schema_is_published() -> None:
    schema = create_contract_app().openapi()
    component_names = set(schema["components"]["schemas"])
    assert "ProblemDetails" in component_names
    problem = schema["components"]["schemas"]["ProblemDetails"]
    required = set(problem["required"])
    assert {"title", "status", "code", "request_id"} <= required


def test_validation_errors_use_problem_json_and_request_id() -> None:
    client = TestClient(create_contract_app())
    response = client.get("/api/v1/projects", headers={"X-Request-Id": "contract-test"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["X-Request-Id"] == "contract-test"
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["request_id"] == "contract-test"


def test_runtime_dependencies_enforce_idempotency_and_if_match() -> None:
    client = TestClient(create_contract_app())
    organization_id = "01900000-0000-7000-8000-000000000001"
    project_id = "01900000-0000-7000-8000-000000000006"

    create_response = client.post(
        "/api/v1/projects",
        headers={"X-Lumi-Organization-Id": organization_id},
        json={
            "workspace_id": "01900000-0000-7000-8000-000000000004",
            "name": "Project",
        },
    )
    assert create_response.status_code == 428
    assert create_response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    patch_response = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"X-Lumi-Organization-Id": organization_id},
        json={"name": "Renamed"},
    )
    assert patch_response.status_code == 428
    assert patch_response.json()["code"] == "IF_MATCH_REQUIRED"


def test_default_gateway_fails_explicitly_instead_of_touching_database() -> None:
    client = TestClient(create_contract_app())
    response = client.get(
        "/api/v1/projects",
        headers={"X-Lumi-Organization-Id": "01900000-0000-7000-8000-000000000001"},
    )
    assert response.status_code == 501
    assert response.json()["code"] == "APPLICATION_SERVICE_NOT_INSTALLED"


def test_transport_contract_has_no_orm_provider_or_agent_runtime_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "lumi_api" / "api"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    forbidden = (
        "sqlalchemy",
        "asyncpg",
        "alembic",
        "langgraph",
        "langchain",
        "openai",
        "anthropic",
        "google.genai",
    )
    for module in forbidden:
        assert f"import {module}" not in source
        assert f"from {module}" not in source
