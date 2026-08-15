#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise SystemExit(f"production runtime contract invalid: missing {path}")
    return target.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production runtime contract invalid: {message}")


def main() -> int:
    cli = text("apps/api/src/lumi_api/cli.py")
    production = text("apps/api/src/lumi_api/production_app.py")
    capabilities = text("apps/api/src/lumi_api/runtime_capabilities.py")
    project_gateway = text("apps/api/src/lumi_api/projects/gateway.py")
    smoke = text("scripts/production-read-only-smoke.py")

    require(
        '"lumi_api.production_app:create_production_app"' in cli and "factory=True" in cli,
        "API CLI must launch the explicit production composition factory",
    )
    require("lumi_api.main:app" not in cli, "health-only lumi_api.main:app must not be a production entrypoint")
    require("ProjectCoreGateway(session_factory)" in production, "production app must install the real SQL project gateway")
    require("create_auth_router(" in production, "production app must install canonical auth")
    require("create_asset_storage_router(" in production, "production app must have a real asset-storage wiring path")
    require('app.get("/health/capabilities"' in production, "machine-readable capability endpoint missing")
    require('app.get("/health/ready"' in production, "release readiness endpoint missing")
    require('app.get("/version"' in production, "production version contract missing")
    require("missing_required_capabilities" in production, "readiness must expose missing launch capabilities")
    require("status_code=503" in production, "incomplete launch capability set must fail readiness")
    require("LAUNCH_REQUIRED_CAPABILITIES" in capabilities, "launch capability contract missing")
    require('if environment in {"staging", "production"}' in capabilities, "staging/production must share the full launch requirement")

    required_names = {
        "auth",
        "projects",
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
    }
    for name in sorted(required_names):
        require(f'"{name}"' in capabilities, f"launch capability {name} missing from canonical contract")

    for forbidden in ("InMemory", "MockProvider", "MockPayment", "sleep infinity"):
        require(forbidden not in production, f"production composition must not depend on test/fake runtime: {forbidden}")

    require("APPLICATION_SERVICE_NOT_INSTALLED" in project_gateway, "known ApiV1 missing-adapter sentinel unexpectedly changed; review required")
    require('"/version"' in smoke, "NODE-72 production smoke no longer checks the version endpoint")
    require('"/health/ready"' in smoke, "NODE-72 production smoke no longer checks readiness")

    print("production runtime composition contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
