from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from lumi_agent_runtime.agent_registry import Node25ToolCatalog
from lumi_agent_runtime.skill_registry import (
    SkillDefinitionValidator,
    SkillEvalEvidence,
    SkillPromotionManager,
    SkillRegistry,
    SkillReleaseError,
    SkillReleaseManifest,
    SkillReleaseRecord,
    SkillReleaseStatus,
    load_release_manifest,
    load_skill_eval_catalog,
    load_skill_schema_catalog,
    load_skills,
)
from lumi_model_gateway.models import Capability
from lumi_tool_gateway.catalog import build_p0_registry

ROOT = Path(__file__).resolve().parents[3]


class PassingGate:
    def evaluate(self, definition):
        return SkillEvalEvidence(True, f"eval://test/{definition.identity}")


class FailingGate:
    def evaluate(self, definition):
        return SkillEvalEvidence(False, "eval://test/failed")


def validator() -> SkillDefinitionValidator:
    return SkillDefinitionValidator(
        tools=Node25ToolCatalog(build_p0_registry()),
        schemas=load_skill_schema_catalog(ROOT / "schemas/skill-io/registry.json"),
        eval_profiles=load_skill_eval_catalog(ROOT / "evals/profiles/skills/registry.json"),
        known_capabilities=frozenset(item.value for item in Capability),
    )


class SkillReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        definitions = load_skills(ROOT / "skills")
        manifest = load_release_manifest(ROOT / "skills/registry.json")
        self.registry = SkillRegistry(definitions, manifest)
        production = self.registry.resolve("creative-direction@production").definition
        self.candidate = replace(
            production,
            version="1.2.0",
            metadata={**production.metadata, "release_note": "candidate test"},
        )
        releases = (*manifest.releases, SkillReleaseRecord(
            skill_id="creative-direction",
            version="1.2.0",
            status=SkillReleaseStatus.CANDIDATE,
            eval_profile=self.candidate.eval_profile,
        ))
        self.manifest = SkillReleaseManifest(
            schema=manifest.schema,
            revision=manifest.revision,
            releases=releases,
            aliases={key: dict(value) for key, value in manifest.aliases.items()},
        )

    def test_failing_eval_blocks_candidate_promotion(self) -> None:
        manager = SkillPromotionManager(validator=validator(), eval_gate=FailingGate())
        with self.assertRaises(SkillReleaseError):
            manager.promote(self.manifest, self.candidate)

    def test_passing_eval_promotes_and_deprecates_previous_production(self) -> None:
        manager = SkillPromotionManager(validator=validator(), eval_gate=PassingGate())
        updated = manager.promote(self.manifest, self.candidate)
        self.assertEqual(updated.revision, self.manifest.revision + 1)
        self.assertEqual(updated.aliases["creative-direction"]["production"], "1.2.0")
        statuses = {
            row.version: row.status
            for row in updated.releases
            if row.skill_id == "creative-direction"
        }
        self.assertEqual(statuses["1.1.0"], SkillReleaseStatus.DEPRECATED)
        self.assertEqual(statuses["1.2.0"], SkillReleaseStatus.PRODUCTION)


if __name__ == "__main__":
    unittest.main()
