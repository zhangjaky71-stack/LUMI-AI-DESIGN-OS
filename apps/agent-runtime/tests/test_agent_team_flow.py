from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from lumi_agent_runtime.agent_team.contracts import (
    TeamArtifactRef,
    TeamCitationRef,
    TeamTaskInput,
    TeamTaskResult,
    TeamTaskStatus,
    team_profile,
)
from lumi_agent_runtime.agent_team.delegation import DelegationRuntimeContext
from lumi_agent_runtime.agent_team.flow import execute_image_team_flow
from lumi_agent_runtime.agent_team.registry import compile_agent_team

ROOT = Path(__file__).resolve().parents[3]


class DeterministicWorker:
    def __init__(self, *, stop_agent: str | None = None) -> None:
        self.calls: list[str] = []
        self.stop_agent = stop_agent

    async def execute(self, definition, task):
        self.calls.append(definition.agent_id)
        if definition.agent_id == self.stop_agent:
            return TeamTaskResult(
                status=TeamTaskStatus.WAITING_EXTERNAL,
                summary=f"{definition.agent_id} waiting on external provider",
                confidence=0.8,
                waiting_reason="provider-request:test",
            )
        citations = ()
        artifacts = ()
        if definition.agent_id in {"brand-strategist", "research-agent"}:
            citations = (
                TeamCitationRef(
                    source_type="knowledge",
                    source_id=f"source-{definition.agent_id}",
                    version="1",
                    locator={"page": 1},
                ),
            )
        if definition.agent_id == "image-generator":
            artifacts = (
                TeamArtifactRef(
                    artifact_id="artifact-image-v1",
                    version="1",
                    kind="image",
                ),
            )
        if definition.agent_id == "image-editor":
            artifacts = (
                TeamArtifactRef(
                    artifact_id="artifact-image-v2",
                    version="2",
                    kind="image",
                ),
            )
        return TeamTaskResult(
            status=TeamTaskStatus.SUCCEEDED,
            summary=f"{definition.agent_id} completed structured stage",
            artifacts=artifacts,
            citations=citations,
            confidence=0.9,
            structured_output={
                "agent_id": definition.agent_id,
                "objective": task.objective,
                "prior_count": len(task.inputs.get("prior_results", {})),
            },
        )


class AgentTeamFlowTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.team = compile_agent_team(repo_root=ROOT)
        root_profile = team_profile(cls.team.resolve("creative-director"))
        cls.runtime = DelegationRuntimeContext(
            allowed_tools=root_profile.delegation_tool_ceiling,
            granted_permissions=root_profile.delegation_permission_ceiling,
            depth=0,
            budget_remaining_usd=20.0,
            deadline_at=datetime(2026, 8, 14, 18, 0, tzinfo=UTC),
        )
        cls.task = TeamTaskInput(
            objective="Create a launch hero image with preserved logo geometry",
            inputs={"brief": {"format": "16:9", "theme": "premium"}},
            constraints=("Preserve logo geometry", "Do not invent campaign facts"),
            expected_output="Final edited image artifact",
            deadline_at=cls.runtime.deadline_at,
            budget_remaining_usd=20.0,
            trace_id="node37-flow",
        )

    async def test_full_image_flow_uses_six_specialists_and_is_deterministic(self) -> None:
        worker_a = DeterministicWorker()
        worker_b = DeterministicWorker()
        first = await execute_image_team_flow(
            team=self.team,
            worker=worker_a,
            task=self.task,
            runtime=self.runtime,
        )
        second = await execute_image_team_flow(
            team=self.team,
            worker=worker_b,
            task=self.task,
            runtime=self.runtime,
        )
        expected = [
            "brand-strategist",
            "research-agent",
            "prompt-engineer",
            "image-generator",
            "critic-agent",
            "image-editor",
        ]
        self.assertEqual(worker_a.calls, expected)
        self.assertEqual(worker_b.calls, expected)
        self.assertEqual(first.status, TeamTaskStatus.SUCCEEDED)
        self.assertEqual(second.status, TeamTaskStatus.SUCCEEDED)
        self.assertEqual(first.results, second.results)
        assert first.final_result is not None
        self.assertEqual(first.final_result.artifacts[0].artifact_id, "artifact-image-v2")
        critic = dict(first.results)["critic-agent"]
        self.assertEqual(critic.artifacts, ())

    async def test_wait_or_failure_stops_downstream_stages(self) -> None:
        worker = DeterministicWorker(stop_agent="video-generator")
        # video-generator is not part of the image flow, proving unrelated waits
        # cannot accidentally affect the image chain.
        outcome = await execute_image_team_flow(
            team=self.team,
            worker=worker,
            task=self.task,
            runtime=self.runtime,
        )
        self.assertEqual(outcome.status, TeamTaskStatus.SUCCEEDED)

    async def test_cancellation_prevents_first_handoff(self) -> None:
        root_profile = team_profile(self.team.resolve("creative-director"))
        cancelled = DelegationRuntimeContext(
            allowed_tools=root_profile.delegation_tool_ceiling,
            granted_permissions=root_profile.delegation_permission_ceiling,
            depth=0,
            budget_remaining_usd=20.0,
            deadline_at=self.runtime.deadline_at,
            cancelled=True,
        )
        worker = DeterministicWorker()
        with self.assertRaisesRegex(PermissionError, "AGENT_TEAM_DELEGATION_CANCELLED"):
            await execute_image_team_flow(
                team=self.team,
                worker=worker,
                task=self.task,
                runtime=cancelled,
            )
        self.assertEqual(worker.calls, [])


if __name__ == "__main__":
    unittest.main()
