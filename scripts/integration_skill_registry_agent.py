from __future__ import annotations

from pathlib import Path

from lumi_agent_runtime.agent_registry import (
    AgentRegistry,
    AgentValidator,
    DependencyResolver,
    Node23ModelPolicyCatalog,
    Node25ToolCatalog,
    load_definitions,
    load_named_catalog,
    load_release_manifest as load_agent_release_manifest,
)
from lumi_agent_runtime.skill_registry import (
    AgentSkillCompatibilityValidator,
    Node31SkillCatalog,
    SkillExecutionContext,
    SkillRegistry,
    load_release_manifest as load_skill_release_manifest,
    load_skills,
)
from lumi_model_gateway.capability_registry import (
    InMemoryCapabilityRegistry,
    compile_registry_seed,
)
from lumi_tool_gateway.catalog import build_p0_registry

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "config/agent-registry/bootstrap-dependencies.v1.json"


def main() -> int:
    skill_registry = SkillRegistry(
        load_skills(ROOT / "skills"),
        load_skill_release_manifest(ROOT / "skills/registry.json"),
    )
    model_snapshot = compile_registry_seed(
        ROOT / "config/model-registry/registry.seed.v1.yaml",
        repository_root=ROOT,
    )
    tool_registry = build_p0_registry()
    dependencies = DependencyResolver(
        model_policies=Node23ModelPolicyCatalog(
            InMemoryCapabilityRegistry(model_snapshot)
        ),
        tools=Node25ToolCatalog(tool_registry),
        skills=Node31SkillCatalog(skill_registry),
        context_policies=load_named_catalog(BOOTSTRAP, "context_policies"),
        budget_policies=load_named_catalog(BOOTSTRAP, "budget_policies"),
        output_schemas=load_named_catalog(BOOTSTRAP, "output_schemas"),
        eval_profiles=load_named_catalog(BOOTSTRAP, "eval_profiles"),
    )
    agent_registry = AgentRegistry(
        load_definitions(ROOT / "agents"),
        load_agent_release_manifest(ROOT / "agents/registry.json"),
        AgentValidator(
            dependencies=dependencies,
            skill_policy=AgentSkillCompatibilityValidator(
                skill_registry,
                available_capabilities=frozenset(),
            ),
        ),
    )
    resolved = agent_registry.resolve("creative-director@production")
    skill_dependency = next(
        item for item in resolved.provenance.dependencies
        if item.kind == "skill" and item.key == "creative-direction"
    )
    exact = skill_registry.resolve("creative-direction@^1").definition
    assert skill_dependency.exact_version == "1.1.0"
    assert skill_dependency.content_hash == exact.content_hash
    assert skill_dependency.source_ref == "NODE-31:creative-direction@1.1.0"
    assert "bootstrap" not in str(skill_dependency.source_ref).lower()

    pack = skill_registry.resolve_pack(
        ("creative-direction@^1",),
        SkillExecutionContext(
            agent_id="creative-director",
            allowed_tools=frozenset(
                {"web.search", "web.fetch", "asset.read", "artifact.query"}
            ),
            granted_permissions=frozenset(),
            available_capabilities=frozenset(),
        ),
    )
    assert pack.skills[-1].definition.identity == "creative-direction@1.1.0"
    assert len(pack.freeze_hash) == 64
    print("NODE-30 Agent Registry -> NODE-31 Skill Registry integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
