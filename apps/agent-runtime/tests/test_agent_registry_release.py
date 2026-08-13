from __future__ import annotations

import unittest
from pathlib import Path

from lumi_agent_runtime.agent_registry import (
    AgentReleaseManager,
    AgentReleaseStatus,
    EvalEvidence,
    load_definitions,
    load_release_manifest,
)
from lumi_agent_runtime.agent_registry.errors import AgentReleaseError

ROOT = Path(__file__).resolve().parents[3]


class PassingGate:
    def evaluate(self, definition):
        return EvalEvidence(
            True,
            f"eval://{definition.agent_id}/{definition.version}/candidate-pass",
        )


class FailingGate:
    def evaluate(self, definition):
        del definition
        return EvalEvidence(False, "eval://failed")


class ValidDefinition:
    def validate(self, definition):
        del definition
        return ()


class AgentReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definitions = {
            item.identity: item for item in load_definitions(ROOT / "agents")
        }
        self.manifest = load_release_manifest(ROOT / "agents/registry.json")

    def test_candidate_promotion_requires_eval_and_moves_alias(self) -> None:
        candidate = self.definitions["creative-director@1.2.0"]
        promoted = AgentReleaseManager(PassingGate(), ValidDefinition()).promote(
            self.manifest,
            candidate,
        )
        self.assertEqual(promoted.revision, 2)
        self.assertEqual(
            promoted.aliases["creative-director"]["production"],
            "1.2.0",
        )
        statuses = {
            item.version: item.status
            for item in promoted.releases
            if item.agent_id == "creative-director"
        }
        self.assertEqual(statuses["1.1.0"], AgentReleaseStatus.DEPRECATED)
        self.assertEqual(statuses["1.2.0"], AgentReleaseStatus.PRODUCTION)

    def test_failed_eval_cannot_promote_candidate(self) -> None:
        candidate = self.definitions["creative-director@1.2.0"]
        with self.assertRaises(AgentReleaseError):
            AgentReleaseManager(FailingGate(), ValidDefinition()).promote(
                self.manifest,
                candidate,
            )

    def test_rollback_repoints_alias_without_mutating_definition(self) -> None:
        candidate = self.definitions["creative-director@1.2.0"]
        old_hash = self.definitions["creative-director@1.1.0"].content_hash
        manager = AgentReleaseManager(PassingGate(), ValidDefinition())
        rolled = manager.rollback(
            manager.promote(self.manifest, candidate),
            "creative-director",
            "1.1.0",
        )
        self.assertEqual(rolled.revision, 3)
        self.assertEqual(
            rolled.aliases["creative-director"]["production"],
            "1.1.0",
        )
        self.assertEqual(
            self.definitions["creative-director@1.1.0"].content_hash,
            old_hash,
        )


if __name__ == "__main__":
    unittest.main()
