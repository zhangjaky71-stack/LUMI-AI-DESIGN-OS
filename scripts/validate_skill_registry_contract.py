from __future__ import annotations

import ast
from pathlib import Path

from lumi_agent_runtime.agent_registry.dependencies import Node25ToolCatalog
from lumi_agent_runtime.skill_registry import (
    SkillDefinitionValidator,
    SkillRegistry,
    SkillReleaseStatus,
    load_release_manifest,
    load_skill_eval_catalog,
    load_skill_schema_catalog,
    load_skills,
)
from lumi_model_gateway.models import Capability
from lumi_tool_gateway.catalog import build_p0_registry

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-31 marker: {marker}")
    return text


def main() -> int:
    definitions = load_skills(ROOT / "skills")
    if len(definitions) != 15 or len({item.skill_id for item in definitions}) != 14:
        raise SystemExit("NODE-31 P0 Skill count must be 14 ids / 15 exact versions")
    manifest = load_release_manifest(ROOT / "skills/registry.json")
    registry = SkillRegistry(definitions, manifest)
    del registry

    validator = SkillDefinitionValidator(
        tools=Node25ToolCatalog(build_p0_registry()),
        schemas=load_skill_schema_catalog(
            ROOT / "schemas/skill-io/registry.json"
        ),
        eval_profiles=load_skill_eval_catalog(
            ROOT / "evals/profiles/skills/registry.json"
        ),
        known_capabilities=frozenset(item.value for item in Capability),
    )
    for definition in definitions:
        validator.validate(definition)
    for release in manifest.releases:
        if release.status == SkillReleaseStatus.PRODUCTION:
            if release.eval_status != "passed" or not release.eval_evidence:
                raise SystemExit(
                    f"production Skill lacks eval evidence: {release.skill_id}@{release.version}"
                )

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/skill_registry/registry.py",
        "resolve_pack",
        "SkillDependencyCycleError",
        "SkillDependencyConflictError",
        "missing_tools",
        "missing_permissions",
        "missing_capabilities",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/skill_registry/selector.py",
        "selector_primary",
        "expected one primary Skill",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/skill_registry/deep_bundle.py",
        'base = f"/skills/{definition.skill_id}"',
        "create_file_data",
        "Skill seed would overwrite existing file",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/skill_registry/deep_factory.py",
        'if "skills" not in parameters',
        '"skills": list(bundle.sources)',
        '"skill_pack_freeze_hash": bundle.pack.freeze_hash',
        '"resolved_skills"',
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/skill_registry/catalog_adapter.py",
        "class Node31SkillCatalog",
        'source_ref=f"NODE-31:{definition.identity}"',
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_registry/validator.py",
        "class AgentSkillPolicy",
        "skill_policy.validate(definition)",
    )
    integration = require(
        "scripts/integration_skill_registry_agent.py",
        "Node31SkillCatalog",
        "AgentSkillCompatibilityValidator",
        'source_ref == "NODE-31:creative-direction@1.1.0"',
    )
    if "load_skill_catalog" in integration:
        raise SystemExit("NODE-31 integration must not use NODE-30 bootstrap Skill catalog")

    package = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/skill_registry"
    forbidden = {
        "asyncpg",
        "sqlalchemy",
        "openai",
        "anthropic",
        "requests",
        "subprocess",
        "docker",
    }
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if roots & forbidden:
                    raise SystemExit(
                        f"Skill Registry imports ambient authority: {path}:{roots & forbidden}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in forbidden:
                    raise SystemExit(
                        f"Skill Registry imports ambient authority: {path}:{root}"
                    )

    print("NODE-31 Skill Registry static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
