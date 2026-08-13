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
from lumi_agent_runtime.recipe_engine import (
    RecipeCompiler,
    RecipeRegistry,
    StepType,
    load_recipes,
    load_release_manifest as load_recipe_release_manifest,
)
from lumi_agent_runtime.skill_registry import (
    AgentSkillCompatibilityValidator,
    Node31SkillCatalog,
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


def build_compiler() -> RecipeCompiler:
    skill_registry = SkillRegistry(
        load_skills(ROOT / "skills"),
        load_skill_release_manifest(ROOT / "skills/registry.json"),
    )
    model_snapshot = compile_registry_seed(
        ROOT / "config/model-registry/registry.seed.v1.yaml",
        repository_root=ROOT,
    )
    dependencies = DependencyResolver(
        model_policies=Node23ModelPolicyCatalog(
            InMemoryCapabilityRegistry(model_snapshot)
        ),
        tools=Node25ToolCatalog(build_p0_registry()),
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
    recipe_registry = RecipeRegistry(
        load_recipes(ROOT / "recipes"),
        load_recipe_release_manifest(ROOT / "recipes/registry.json"),
    )
    return RecipeCompiler(
        recipes=recipe_registry,
        agents=agent_registry,
        skills=skill_registry,
    )


def main() -> int:
    compiler = build_compiler()
    recipe_ids = (
        "quick-image",
        "poster-campaign",
        "brand-identity",
        "product-visuals",
        "social-kit",
        "image-edit",
        "video-campaign",
    )
    compiled = {
        recipe_id: compiler.compile(f"{recipe_id}@production")
        for recipe_id in recipe_ids
    }
    for recipe_id, recipe in compiled.items():
        assert recipe.definition.version == "1.0.0", recipe_id
        assert len(recipe.task_graph.content_hash) == 64, recipe_id
        assert len(recipe.provenance.freeze_hash) == 64, recipe_id
        again = compiler.compile(f"{recipe_id}@production")
        assert again.task_graph.content_hash == recipe.task_graph.content_hash, recipe_id
        assert again.provenance.freeze_hash == recipe.provenance.freeze_hash, recipe_id

    quick = compiled["quick-image"]
    agents = {
        (item.agent_id, item.exact_version)
        for item in quick.provenance.agents
    }
    assert ("creative-director", "1.1.0") in agents
    assert ("critic", "1.0.0") in agents
    skills = {
        (item.skill_id, item.exact_version)
        for item in quick.provenance.skills
    }
    assert ("creative-direction", "1.1.0") in skills
    assert ("visual-critique", "1.0.0") in skills
    quick_tasks = {item.task_key: item for item in quick.task_graph.tasks}
    assert quick_tasks["generate"].metadata["media_operation"] == "image.generate"
    assert quick_tasks["finalize"].owner == "DETERMINISTIC_SERVICE:artifact.finalize"

    product = compiled["product-visuals"]
    product_tasks = {item.task_key: item for item in product.task_graph.tasks}
    for child in ("renders.hero", "renders.detail", "renders.context"):
        assert product_tasks[child].budget_limit_usd == "2"
        assert product_tasks[child].metadata["parallel_group"] == "renders"
    join = product_tasks["renders"]
    assert join.step_type == StepType.PARALLEL
    assert join.depends_on == (
        "renders.hero",
        "renders.detail",
        "renders.context",
    )
    assert join.budget_limit_usd == "6"
    assert join.metadata["join_policy"] == "ALL"
    approval = product_tasks["approve"].metadata["approval"]
    assert isinstance(approval, dict)
    assert approval["interrupt_hook"] == "NODE-28:approval_interrupt"
    assert approval["decision_authority"] == "LUMI_APPROVAL_SERVICE"
    assert approval["resume_mapping"] == {
        "approve": "approved",
        "reject": "rejected",
    }

    poster = compiled["poster-campaign"]
    poster_tasks = {item.task_key: item for item in poster.task_graph.tasks}
    for index in range(3):
        child = poster_tasks[f"concepts[{index}]"]
        assert child.budget_limit_usd == "2"
        assert child.metadata["foreach_count"] == 3
    assert poster_tasks["concepts"].depends_on == (
        "concepts[0]",
        "concepts[1]",
        "concepts[2]",
    )
    assert poster_tasks["concepts"].metadata["join_policy"] == "ALL"

    video = compiled["video-campaign"]
    video_tasks = {item.task_key: item for item in video.task_graph.tasks}
    assert video_tasks["generate"].metadata["media_operation"] == "video.generate"
    assert video_tasks["quality"].metadata["max_repair_iterations"] == 0

    print("NODE-32 NODE-23/25/30/31 Recipe compiler integration: PASS (7 recipes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
