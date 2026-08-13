from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_agent_runtime.recipe_engine import (
    RecipeRegistry,
    RecipeReleaseStatus,
    StepType,
    load_recipes,
    load_release_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine"
EXPECTED_RECIPES = {
    "quick-image",
    "poster-campaign",
    "brand-identity",
    "product-visuals",
    "social-kit",
    "image-edit",
    "video-campaign",
}
EXPECTED_STEP_TYPES = {
    "DETERMINISTIC",
    "AGENT",
    "PARALLEL",
    "FOREACH",
    "APPROVAL",
    "QUALITY_GATE",
    "MEDIA_JOB",
    "SUBRECIPE",
    "FINALIZE",
}
FORBIDDEN_IMPORTS = {
    "asyncpg",
    "sqlalchemy",
    "psycopg",
    "requests",
    "subprocess",
    "docker",
    "openai",
    "anthropic",
    "google",
}
FORBIDDEN_BUILTINS = {"eval", "exec", "compile"}


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-32 marker: {marker}")
    return text


def main() -> int:
    definitions = load_recipes(ROOT / "recipes")
    manifest = load_release_manifest(ROOT / "recipes/registry.json")
    registry = RecipeRegistry(definitions, manifest)
    if {item.recipe_id for item in definitions} != EXPECTED_RECIPES:
        raise SystemExit("NODE-32 initial Recipe set differs from required seven")
    if len(definitions) != 7:
        raise SystemExit("NODE-32 must have exactly seven initial exact Recipe versions")
    for recipe_id in sorted(EXPECTED_RECIPES):
        resolved = registry.resolve(f"{recipe_id}@production")
        if resolved.release_status != RecipeReleaseStatus.PRODUCTION:
            raise SystemExit(f"Recipe is not production: {recipe_id}")
        if resolved.definition.version != "1.0.0":
            raise SystemExit(f"Recipe exact version unexpected: {recipe_id}")
    for release in manifest.releases:
        if release.status == RecipeReleaseStatus.PRODUCTION:
            if release.eval_status != "passed" or not release.eval_evidence:
                raise SystemExit(
                    f"production Recipe lacks eval evidence: "
                    f"{release.recipe_id}@{release.version}"
                )
    if {item.value for item in StepType} != EXPECTED_STEP_TYPES:
        raise SystemExit("NODE-32 StepType V1 contract drifted")

    recipe_schema = json.loads(
        (ROOT / "schemas/recipe/recipe.schema.json").read_text(encoding="utf-8")
    )
    if recipe_schema.get("$id") != "urn:lumi:recipe:v1":
        raise SystemExit("NODE-32 Recipe DSL schema identity invalid")
    schema_step_types = set(
        recipe_schema["$defs"]["step"]["properties"]["type"]["enum"]
    )
    if {item.upper() for item in schema_step_types} != EXPECTED_STEP_TYPES:
        raise SystemExit("NODE-32 Recipe DSL Step type enum drifted")

    eval_registry = json.loads(
        (ROOT / "evals/profiles/recipes/registry.json").read_text(encoding="utf-8")
    )
    if eval_registry.get("schema") != "lumi.recipe-eval-profile-registry.v1":
        raise SystemExit("NODE-32 Recipe eval profile registry invalid")
    known_profiles = set(eval_registry.get("profiles", {}))
    declared_profiles = {
        str(item.metadata.get("eval_profile"))
        for item in definitions
    }
    if declared_profiles - known_profiles:
        raise SystemExit(
            f"Recipe eval profile missing: {sorted(declared_profiles - known_profiles)}"
        )

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/loader.py",
        "_FORBIDDEN_KEYS",
        "RECIPE_RAW_URL_FORBIDDEN",
        "RECIPE_RAW_SQL_FORBIDDEN",
        "1 <= step.foreach_count <= 8",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/expression.py",
        'ast.parse(expression, mode="eval")',
        "RECIPE_EXPRESSION_NODE_FORBIDDEN",
        "_ALLOWED_ROOTS",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/resolution.py",
        "self.agents.resolve(step.agent_ref)",
        "self.skills.resolve(requested_skill)",
        "Recipe Skill expands Agent definition",
        "Recipe Skill exact version differs from Agent freeze",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/atomic.py",
        '"interrupt_hook": "NODE-28:approval_interrupt"',
        '"decision_authority": "LUMI_APPROVAL_SERVICE"',
        "max_repair_iterations",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/containers.py",
        "parallel requires total budget and explicit budget split",
        "parallel budget split must equal total budget",
        '"join_policy": JoinPolicy.ALL.value',
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/compiler.py",
        '"node33_contract": "TaskGraphTemplate:v1"',
        "recipe_definition_hash=definition.content_hash",
        "task_graph_template_hash=graph.content_hash",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/release.py",
        "only CANDIDATE Recipe can be promoted",
        "production promotion blocked by benchmark/eval gate",
        "RecipeReleaseStatus.DEPRECATED",
        '"production"',
    )

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = roots & FORBIDDEN_IMPORTS
                if bad:
                    raise SystemExit(
                        f"Recipe Engine imports ambient authority: {path}:{sorted(bad)}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    raise SystemExit(
                        f"Recipe Engine imports ambient authority: {path}:{root}"
                    )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_BUILTINS:
                    raise SystemExit(
                        f"Recipe Engine calls forbidden builtin: {path}:{node.func.id}"
                    )

    for definition in definitions:
        for step in definition.steps:
            if step.step_type == StepType.PARALLEL:
                policy = step.parallel
                if policy is None or policy.budget_limit_usd is None:
                    raise SystemExit(
                        f"parallel Recipe lacks bounded budget: "
                        f"{definition.identity}:{step.step_id}"
                    )
            if step.step_type == StepType.FOREACH:
                if step.foreach_count is None or not 1 <= step.foreach_count <= 8:
                    raise SystemExit(
                        f"foreach Recipe is unbounded: "
                        f"{definition.identity}:{step.step_id}"
                    )

    print("NODE-32 Workflow / Recipe Engine static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
