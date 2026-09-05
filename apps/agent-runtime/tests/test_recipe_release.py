from __future__ import annotations

import unittest
from typing import cast

from lumi_agent_runtime.recipe_engine import (
    RecipeDefinition,
    RecipeDefinitionValidator,
    RecipeEvalEvidence,
    RecipePromotionManager,
    RecipeReleaseError,
    RecipeReleaseManifest,
    RecipeReleaseRecord,
    RecipeReleaseStatus,
    RecipeStep,
    StepType,
)


class PassingGate:
    def evaluate(self, definition: RecipeDefinition) -> RecipeEvalEvidence:
        return RecipeEvalEvidence(True, f"eval://test/{definition.identity}")


class FailingGate:
    def evaluate(self, definition: RecipeDefinition) -> RecipeEvalEvidence:
        return RecipeEvalEvidence(False, f"eval://test/{definition.identity}/failed")


class ValidatorFixture:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, definition: RecipeDefinition) -> None:
        self.calls += 1
        if definition.metadata.get("eval_profile") != "candidate-v1":
            raise RecipeReleaseError("fixture eval profile mismatch")


def candidate() -> RecipeDefinition:
    return RecipeDefinition(
        recipe_id="candidate-recipe",
        version="1.1.0",
        inputs=("brief",),
        steps=(
            RecipeStep(
                step_id="finalize",
                step_type=StepType.FINALIZE,
                service_key="artifact.finalize",
            ),
        ),
        metadata={"eval_profile": "candidate-v1"},
    )


def manifest() -> RecipeReleaseManifest:
    return RecipeReleaseManifest(
        schema="lumi.recipe-registry.release.v1",
        revision=7,
        releases=(
            RecipeReleaseRecord(
                recipe_id="candidate-recipe",
                version="1.0.0",
                status=RecipeReleaseStatus.PRODUCTION,
                eval_profile="candidate-v1",
                eval_status="passed",
                eval_evidence="eval://old",
            ),
            RecipeReleaseRecord(
                recipe_id="candidate-recipe",
                version="1.1.0",
                status=RecipeReleaseStatus.CANDIDATE,
                eval_profile="candidate-v1",
            ),
        ),
        aliases={"candidate-recipe": {"production": "1.0.0"}},
    )


class RecipeReleaseTests(unittest.TestCase):
    def test_failing_benchmark_blocks_promotion(self) -> None:
        fixture = ValidatorFixture()
        manager = RecipePromotionManager(
            validator=cast(RecipeDefinitionValidator, fixture),
            eval_gate=FailingGate(),
        )
        with self.assertRaises(RecipeReleaseError):
            manager.promote(manifest(), candidate())
        self.assertEqual(fixture.calls, 1)

    def test_passing_benchmark_promotes_and_deprecates_previous(self) -> None:
        fixture = ValidatorFixture()
        manager = RecipePromotionManager(
            validator=cast(RecipeDefinitionValidator, fixture),
            eval_gate=PassingGate(),
        )
        updated = manager.promote(manifest(), candidate())
        self.assertEqual(updated.revision, 8)
        self.assertEqual(
            updated.aliases["candidate-recipe"]["production"],
            "1.1.0",
        )
        statuses = {row.version: row.status for row in updated.releases}
        self.assertEqual(statuses["1.0.0"], RecipeReleaseStatus.DEPRECATED)
        self.assertEqual(statuses["1.1.0"], RecipeReleaseStatus.PRODUCTION)
        promoted = next(row for row in updated.releases if row.version == "1.1.0")
        self.assertEqual(promoted.eval_status, "passed")
        self.assertEqual(promoted.eval_evidence, "eval://test/candidate-recipe@1.1.0")


if __name__ == "__main__":
    unittest.main()
