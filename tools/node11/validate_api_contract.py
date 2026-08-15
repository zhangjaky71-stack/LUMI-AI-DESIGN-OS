from __future__ import annotations

import ast
from pathlib import Path

from lumi_api.api.v1.app import create_contract_app

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api" / "src" / "lumi_api" / "api" / "v1"

EXPECTED_PATHS = {
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
FORBIDDEN_IMPORT_ROOTS = {
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "langgraph",
    "langchain",
    "openai",
    "anthropic",
    "boto3",
}


def parameter_names(operation: dict[str, object]) -> set[str]:
    parameters = operation.get("parameters", [])
    assert isinstance(parameters, list)
    return {
        str(parameter["name"])
        for parameter in parameters
        if isinstance(parameter, dict) and "name" in parameter
    }


def assert_openapi_contract() -> None:
    schema = create_contract_app().openapi()
    paths = schema["paths"]
    assert set(paths) == EXPECTED_PATHS

    for path_item in paths.values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            assert "X-Organization-ID" in parameter_names(operation)

    required_idempotency = (
        paths["/api/v1/projects"]["post"],
        paths["/api/v1/projects/{project_id}/tasks"]["post"],
        paths["/api/v1/projects/{project_id}/agent-runs"]["post"],
        paths["/api/v1/agent-runs/{agent_run_id}/cancel"]["post"],
        paths["/api/v1/projects/{project_id}/generations"]["post"],
    )
    for operation in required_idempotency:
        assert "Idempotency-Key" in parameter_names(operation)

    assert "If-Match" in parameter_names(paths["/api/v1/projects/{project_id}"]["patch"])
    assert "If-Match" in parameter_names(
        paths["/api/v1/projects/{project_id}/transitions"]["post"]
    )

    problem = schema["components"]["schemas"]["ProblemDetail"]
    required_problem_fields = {"title", "status", "detail", "code", "request_id"}
    assert required_problem_fields.issubset(set(problem["required"]))


def assert_transport_layer_is_adapter_only() -> None:
    discovered: set[str] = set()
    forbidden_internal_fragments: list[str] = []

    for path in API_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                discovered.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                discovered.add(node.module.split(".")[0])
                if "persistence" in node.module or "providers" in node.module:
                    forbidden_internal_fragments.append(f"{path.name}:{node.module}")

    assert discovered.isdisjoint(FORBIDDEN_IMPORT_ROOTS), discovered & FORBIDDEN_IMPORT_ROOTS
    assert not forbidden_internal_fragments, forbidden_internal_fragments


def main() -> None:
    assert_openapi_contract()
    assert_transport_layer_is_adapter_only()
    print(
        "NODE-11 API contract validation PASS: "
        f"{len(EXPECTED_PATHS)} paths, tenant/idempotency/concurrency headers, "
        "Problem Details, no ORM/provider/LangGraph leakage"
    )


if __name__ == "__main__":
    main()
