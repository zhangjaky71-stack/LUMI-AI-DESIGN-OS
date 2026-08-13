from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-30 marker: {marker}")
    return text


def main() -> int:
    schema = json.loads((ROOT / "schemas/agent-definition-v1.schema.json").read_text())
    required = set(schema.get("required", []))
    expected = {
        "id", "version", "role", "description", "model_policy", "tools",
        "skills", "context_policy", "memory_policy", "budget_policy",
        "permissions", "output_schema", "eval_profile",
    }
    if not expected <= required:
        raise SystemExit("AgentDefinition schema misses required fields")

    agent_files = sorted((ROOT / "agents").glob("*/*/agent.yaml"))
    if len(agent_files) < 5:
        raise SystemExit("NODE-30 requires versioned sample AgentDefinitions")
    route_payload = json.loads((ROOT / "docs/models/route-candidates.json").read_text())
    model_policies = {str(item["route"]) for item in route_payload["routes"]}
    for path in agent_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if path.parent.name != payload["version"] or path.parent.parent.name != payload["id"]:
            raise SystemExit(f"Agent path identity mismatch: {path}")
        if payload["model_policy"] not in model_policies:
            raise SystemExit(f"Agent uses unknown NODE-23 model policy: {path}")
        prompt = (path.parent / "system.md").read_text(encoding="utf-8")
        for marker in ("{{", "{%", "${"):
            if marker in prompt:
                raise SystemExit(f"dynamic prompt interpolation forbidden: {path}")

    manifest = json.loads((ROOT / "agents/registry.json").read_text())
    if manifest.get("schema") != "lumi.agent-registry.release.v1":
        raise SystemExit("Agent release manifest schema invalid")
    releases = {
        (str(item["id"]), str(item["version"])): str(item["status"])
        for item in manifest["releases"]
    }
    for agent_id, aliases in manifest["aliases"].items():
        production = aliases.get("production")
        if production is None or releases.get((agent_id, production)) != "PRODUCTION":
            raise SystemExit(f"production alias is not bound to PRODUCTION: {agent_id}")

    bootstrap = json.loads(
        (ROOT / "config/agent-registry/bootstrap-dependencies.v1.json").read_text()
    )
    for section in ("skills", "context_policies", "budget_policies", "output_schemas", "eval_profiles"):
        if not bootstrap.get(section):
            raise SystemExit(f"bootstrap dependency section missing: {section}")
    for row in bootstrap["output_schemas"].values():
        source = row.get("source_ref")
        if not source or not (ROOT / source).exists():
            raise SystemExit(f"output schema source missing: {source}")
    for row in bootstrap["eval_profiles"].values():
        source = row.get("source_ref")
        if not source or not (ROOT / source).exists():
            raise SystemExit(f"eval profile source missing: {source}")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_registry/registry.py",
        "class AgentRegistry",
        "production_versions",
        "resolve_exact_for_resume",
        "release_manifest_revision",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_registry/release.py",
        "class AgentReleaseManager",
        "self.validator.validate(definition)",
        "production promotion blocked by eval release gate",
        "rollback target must be a previously released production version",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_registry/dependencies.py",
        "class Node23ModelPolicyCatalog",
        "class Node25ToolCatalog",
        "class DependencyResolver",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_registry/deep_adapter.py",
        "agent_registry_definition_hash",
        "agent_registry_provenance_hash",
        "DeepAgentDefinition",
    )
    require(
        "apps/api/alembic/versions/0014_agent_registry_provenance.py",
        "CREATE TABLE agent_run_provenance",
        "REVOKE UPDATE, DELETE",
        "GRANT SELECT, INSERT",
        "provenance_hash",
    )

    package_root = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/agent_registry"
    forbidden = {"openai", "anthropic", "requests", "subprocess", "asyncpg", "sqlalchemy"}
    for path in package_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".", 1)[0] for alias in node.names}
                if names & forbidden:
                    raise SystemExit(f"Agent Registry imports ambient authority: {path}:{names & forbidden}")
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in forbidden:
                    raise SystemExit(f"Agent Registry imports ambient authority: {path}:{root}")

    print("NODE-30 Agent Registry static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
