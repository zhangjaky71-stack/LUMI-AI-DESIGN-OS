from __future__ import annotations

from fastapi.testclient import TestClient

from lumi_api import cli
from lumi_api.config import Settings
from lumi_api.production_app import create_production_app
from lumi_api.projects.gateway import ProjectCoreGateway
from lumi_api.runtime_capabilities import LAUNCH_REQUIRED_CAPABILITIES


def settings(environment: str = "test") -> Settings:
    return Settings(
        lumi_env=environment,
        lumi_version="runtime-contract",
        database_url="postgresql+asyncpg://lumi:lumi@127.0.0.1:5432/lumi_contract",
        s3_bucket=None,
    )


def test_cli_launches_explicit_production_factory(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(target: str, **kwargs) -> None:
        captured["target"] = target
        captured.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    cli.main()

    assert captured["target"] == "lumi_api.production_app:create_production_app"
    assert captured["factory"] is True
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8000


def test_production_composition_installs_real_project_gateway_and_auth_routes() -> None:
    app = create_production_app(settings("test"))

    assert isinstance(app.state.api_v1_gateway, ProjectCoreGateway)
    paths = {route.path for route in app.routes}
    assert "/api/v1/projects" in paths
    assert any(path.startswith("/auth/") for path in paths)
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/health/capabilities" in paths


def test_development_requires_only_real_core_capabilities() -> None:
    app = create_production_app(settings("test"))
    snapshot = app.state.runtime_capabilities.snapshot()

    assert snapshot["ready"] is True
    assert snapshot["required"] == ["auth", "projects"]
    assert snapshot["missing_required"] == []
    assert app.state.runtime_capabilities.get("auth").state == "READY"
    assert app.state.runtime_capabilities.get("projects").state == "READY"
    assert app.state.runtime_capabilities.get("generation").state == "MISSING"


def test_staging_and_production_fail_closed_until_full_launch_capabilities_exist() -> None:
    for environment in ("staging", "production"):
        app = create_production_app(settings(environment))
        registry = app.state.runtime_capabilities

        assert registry.required == LAUNCH_REQUIRED_CAPABILITIES
        assert registry.ready_for_release is False
        missing = set(registry.missing_required)
        assert {
            "asset_upload",
            "artifact_versions",
            "agent_runs",
            "tasks",
            "generation",
            "approval",
            "billing",
            "collaboration",
            "governance",
            "admin",
        }.issubset(missing)


def test_capability_endpoint_is_machine_readable_without_touching_database() -> None:
    app = create_production_app(settings("production"))
    with TestClient(app) as client:
        response = client.get("/health/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["environment"] == "production"
    assert "generation" in payload["missing_required"]
    assert "billing" in payload["missing_required"]
