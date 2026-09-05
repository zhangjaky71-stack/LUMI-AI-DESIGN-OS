from __future__ import annotations

import unittest
from pathlib import Path

from lumi_agent_runtime.recipe_engine import (
    LoopPolicy,
    RecipeCycleError,
    RecipeDefinition,
    RecipeRegistry,
    RecipeStep,
    StepType,
    load_recipes,
    load_release_manifest,
)
from lumi_agent_runtime.recipe_engine.errors import RecipeDependencyError
from lumi_agent_runtime.recipe_engine.validation import topological_steps

ROOT = Path(__file__).resolve().parents[3]


class RecipeDagTests(unittest.TestCase):
    def test_initial_catalog_has_seven_production_recipes(self) -> None:
        definitions = load_recipes(ROOT / "recipes")
        self.assertEqual(len(definitions), 7)
        registry = RecipeRegistry(
            definitions,
            load_release_manifest(ROOT / "recipes/registry.json"),
        )
        self.assertEqual(registry.resolve("quick-image@^1").definition.version, "1.0.0")
        self.assertEqual(
            registry.resolve("poster-campaign@production").definition.version,
            "1.0.0",
        )

    def test_loop_is_always_bounded(self) -> None:
        policy = LoopPolicy(
            max_iterations=3,
            budget_limit_usd="2",
            stop_condition="steps.critic.score >= 80",
        )
        self.assertEqual(policy.max_iterations, 3)
        with self.assertRaises(ValueError):
            LoopPolicy(max_iterations=0)
        with self.assertRaises(ValueError):
            LoopPolicy(max_iterations=6)

    def test_missing_dependency_is_rejected(self) -> None:
        definition = RecipeDefinition(
            recipe_id="invalid-dependency",
            version="1.0.0",
            inputs=("brief",),
            steps=(
                RecipeStep(
                    step_id="finalize",
                    step_type=StepType.FINALIZE,
                    service_key="artifact.finalize",
                    depends_on=("missing",),
                ),
            ),
        )
        with self.assertRaises(RecipeDependencyError):
            topological_steps(definition)

    def test_cycle_is_rejected(self) -> None:
        definition = RecipeDefinition(
            recipe_id="cycle-test",
            version="1.0.0",
            inputs=("brief",),
            steps=(
                RecipeStep(
                    step_id="first",
                    step_type=StepType.DETERMINISTIC,
                    service_key="artifact.finalize",
                    depends_on=("second",),
                ),
                RecipeStep(
                    step_id="second",
                    step_type=StepType.DETERMINISTIC,
                    service_key="artifact.finalize",
                    depends_on=("first",),
                ),
            ),
        )
        with self.assertRaises(RecipeCycleError):
            topological_steps(definition)


if __name__ == "__main__":
    unittest.main()
