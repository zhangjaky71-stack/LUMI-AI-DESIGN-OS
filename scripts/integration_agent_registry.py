from __future__ import annotations

from pathlib import Path

from lumi_agent_runtime.agent_registry import (
    AgentRegistry,
    AgentValidator,
    DependencyResolver,
    Node23ModelPolicyCatalog,
    Node25ToolCatalog,
    load_bootstrap_catalog,
    load_definitions,
    load_release_manifest,
    to_deep_agent_definition,
)
from lumi_model_gateway.capability_registry import InMemoryCapabilityRegistry, compile_registry_seed
from lumi_tool_gateway.catalog import build_p0_registry

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "config/agent-registry/bootstrap-dependencies.v1.json"


def main() -> int:
    snapshot = compile_registry_seed(
        ROOT / "config/model-registry/registry.seed.v1.yaml",
        repository_root=ROOT,
    )
    dependencies = DependencyResolver(
        model_policies=Node23ModelPolicyCatalog(InMemoryCapabilityRegistry(snapshot)),
        tools=Node25ToolCatalog(build_p0_registry()),
        skills=load_bootstrap_catalog(BOOTSTRAP, "skills"),
        context_policies=load_bootstrap_catalog(BOOTSTRAP, "context_policies"),
        budget_policies=load_bootstrap_catalog(BOOTSTRAP, "budget_policies"),
        output_schemas=load_bootstrap_catalog(BOOTSTRAP, "output_schemas"),
        eval_profiles=load_bootstrap_catalog(BOOTSTRAP, "eval_profiles"),
    )
    registry = AgentRegistry(
        load_definitions(ROOT / "agents"),
        load_release_manifest(ROOT / "agents/registry.json"),
        AgentValidator(dependencies=dependencies),
    )
    director = registry.resolve("creative-director@^1")
    assert director.definition.version == "1.1.0"
    assert any(
        item.kind == "model_policy"
        and item.key == "reasoning.director"
        and item.content_hash == snapshot.content_hash
        for item in director.provenance.dependencies
    )
    exact_tools = {
        item.key: item.exact_version
        for item in director.provenance.dependencies
        if item.kind == "tool"
    }
    assert exact_tools["web.search"] == "1.0.0"
    assert exact_tools["web.fetch"] == "1.0.0"
    skill = next(item for item in director.provenance.dependencies if item.kind == "skill")
    assert skill.exact_version == "1.1.0"
    deep = to_deep_agent_definition(director)
    assert deep.metadata["agent_registry_definition_hash"] == director.definition.content_hash
    assert deep.metadata["agent_registry_provenance_hash"] == director.provenance.freeze_hash
    deprecated = registry.resolve_exact_for_resume("creative-director", "1.0.0")
    assert deprecated.provenance.release_status.value == "DEPRECATED"
    print("NODE-30 Agent Registry -> NODE-23/25/29 integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
