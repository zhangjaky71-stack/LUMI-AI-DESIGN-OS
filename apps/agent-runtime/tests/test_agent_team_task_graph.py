from __future__ import annotations

import unittest
from pathlib import Path

from lumi_agent_runtime.agent_team.registry import compile_agent_team
from lumi_agent_runtime.agent_team.task_graph import (
    TeamGraphStep,
    TeamTaskGraphPlan,
    image_team_task_graph,
)

ROOT = Path(__file__).resolve().parents[3]


class AgentTeamTaskGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.team = compile_agent_team(repo_root=ROOT)

    def test_image_graph_has_six_specialists_and_explicit_dependencies(self) -> None:
        graph = image_team_task_graph(self.team)
        self.assertEqual(len(graph.steps), 6)
        self.assertEqual(
            [step.agent_id for step in graph.steps],
            [
                "brand-strategist",
                "research-agent",
                "prompt-engineer",
                "image-generator",
                "critic-agent",
                "image-editor",
            ],
        )
        by_id = {step.step_id: step for step in graph.steps}
        self.assertEqual(by_id["research"].depends_on, ("brand",))
        self.assertEqual(by_id["prompt"].depends_on, ("brand", "research"))
        self.assertEqual(by_id["critic"].depends_on, ("generate",))
        self.assertEqual(by_id["edit"].depends_on, ("generate", "critic"))

    def test_template_uses_node33_agent_owner_keys(self) -> None:
        template = image_team_task_graph(self.team).as_task_graph_template()
        owners = [step["owner"] for step in template["steps"]]
        self.assertTrue(all(owner.startswith("AGENT:") for owner in owners))
        self.assertTrue(all(owner.endswith("@2.0.0") for owner in owners))
        self.assertTrue(all(step["task_type"] == "AGENT_TEAM_HANDOFF" for step in template["steps"]))

    def test_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "AGENT_TEAM_GRAPH_CYCLE"):
            TeamTaskGraphPlan(
                graph_key="cycle",
                steps=(
                    TeamGraphStep("a", "brand-strategist", ("b",)),
                    TeamGraphStep("b", "research-agent", ("a",)),
                    TeamGraphStep("c", "prompt-engineer", ()),
                    TeamGraphStep("d", "critic-agent", ()),
                ),
            )

    def test_parallel_same_slot_writes_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "AGENT_TEAM_GRAPH_CONCURRENT_ARTIFACT_WRITE",
        ):
            TeamTaskGraphPlan(
                graph_key="parallel-writers",
                steps=(
                    TeamGraphStep("a", "brand-strategist", ()),
                    TeamGraphStep(
                        "b",
                        "image-generator",
                        ("a",),
                        writes_artifact_slot="same",
                    ),
                    TeamGraphStep(
                        "c",
                        "image-editor",
                        ("a",),
                        writes_artifact_slot="same",
                    ),
                    TeamGraphStep("d", "critic-agent", ("b", "c")),
                ),
            )


if __name__ == "__main__":
    unittest.main()
