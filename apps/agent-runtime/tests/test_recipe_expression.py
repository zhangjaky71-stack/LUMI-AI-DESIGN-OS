from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lumi_agent_runtime.recipe_engine import (
    RecipeExpressionError,
    RecipeSecurityError,
    evaluate_expression,
    load_recipe,
    validate_expression,
)


class RecipeExpressionTests(unittest.TestCase):
    def test_safe_expression_evaluates_without_eval(self) -> None:
        expression = "steps.critic.score < 80 and run.repair_allowed"
        self.assertEqual(validate_expression(expression), expression)
        self.assertTrue(
            evaluate_expression(
                expression,
                {
                    "inputs": {},
                    "project": {},
                    "steps": {"critic": {"score": 72}},
                    "run": {"repair_allowed": True},
                },
            )
        )

    def test_unsafe_nodes_are_forbidden(self) -> None:
        for expression in (
            "__import__('os')",
            "steps['critic'].score < 80",
            "open('x')",
            "steps.critic.score + 1 < 80",
        ):
            with self.assertRaises(RecipeExpressionError):
                validate_expression(expression)

    def test_loader_rejects_arbitrary_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = Path(tmp) / "unsafe" / "1.0.0"
            version_dir.mkdir(parents=True)
            (version_dir / "recipe.yaml").write_text(
                '{"id":"unsafe","version":"1.0.0","inputs":["brief"],'
                '"script":"print(1)","steps":[{"id":"x","type":"finalize",'
                '"service":"artifact.finalize"}]}',
                encoding="utf-8",
            )
            with self.assertRaises(RecipeSecurityError):
                load_recipe(version_dir)

    def test_loader_rejects_raw_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = Path(tmp) / "unsafe-url" / "1.0.0"
            version_dir.mkdir(parents=True)
            (version_dir / "recipe.yaml").write_text(
                '{"id":"unsafe-url","version":"1.0.0","inputs":["brief"],'
                '"metadata":{"source":"https://example.com/x"},'
                '"steps":[{"id":"x","type":"finalize",'
                '"service":"artifact.finalize"}]}',
                encoding="utf-8",
            )
            with self.assertRaises(RecipeSecurityError):
                load_recipe(version_dir)


if __name__ == "__main__":
    unittest.main()
