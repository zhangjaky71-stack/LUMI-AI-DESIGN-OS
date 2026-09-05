from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

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
from lumi_agent_runtime.agent_team.task_graph import image_team_task_graph
from lumi_model_gateway import Capability, MockProvider, ModelRequest, ResultStatus

ROOT = Path(__file__).resolve().parents[1]


class DeterministicTeamWorker:
    async def execute(self, definition, task):
        citations = ()
        artifacts = ()
        if definition.agent_id in {"brand-strategist", "research-agent"}:
            citations = (
                TeamCitationRef(
                    source_type="knowledge",
                    source_id=f"node37-{definition.agent_id}",
                    version="1",
                    locator={"page": 1},
                ),
            )
        if definition.agent_id == "image-generator":
            artifacts = (
                TeamArtifactRef("node37-image", "1", "image"),
            )
        if definition.agent_id == "image-editor":
            artifacts = (
                TeamArtifactRef("node37-image", "2", "image"),
            )
        return TeamTaskResult(
            status=TeamTaskStatus.SUCCEEDED,
            summary=f"{definition.agent_id} deterministic success",
            artifacts=artifacts,
            citations=citations,
            confidence=0.9,
            structured_output={
                "agent_id": definition.agent_id,
                "objective": task.objective,
                "prior_count": len(task.inputs.get("prior_results", {})),
            },
        )


async def main_async() -> None:
    team = compile_agent_team(repo_root=ROOT)
    if len(team.definitions) != 16:
        raise AssertionError("NODE-37 did not compile exactly 16 agents")

    root = team.resolve("creative-director")
    provider_probe = await _exercise_mock_provider(root.model_policy)
    if not provider_probe:
        raise AssertionError("NODE-37 MockProvider probe returned no evidence")

    graph = image_team_task_graph(team)
    template = graph.as_task_graph_template()
    if len(template["steps"]) < 4:
        raise AssertionError("NODE-37 TaskGraph image flow has fewer than four agents")
    owners = [step["owner"] for step in template["steps"]]
    if len(set(owners)) < 4:
        raise AssertionError("NODE-37 TaskGraph image flow lacks specialist diversity")

    profile = team_profile(root)
    deadline = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
    runtime = DelegationRuntimeContext(
        allowed_tools=profile.delegation_tool_ceiling,
        granted_permissions=profile.delegation_permission_ceiling,
        depth=0,
        budget_remaining_usd=20.0,
        deadline_at=deadline,
    )
    task = TeamTaskInput(
        objective="Create a premium launch hero while preserving logo geometry",
        inputs={
            "brief": {
                "format": "16:9",
                "required_text": "LUMI",
                "style": "premium minimal",
            },
            "provider_probe": provider_probe,
        },
        constraints=(
            "Preserve logo geometry",
            "Do not invent campaign facts",
        ),
        expected_output="Final edited image artifact",
        deadline_at=deadline,
        budget_remaining_usd=20.0,
        trace_id="node37-e2e",
    )

    first = await execute_image_team_flow(
        team=team,
        worker=DeterministicTeamWorker(),
        task=task,
        runtime=runtime,
    )
    second = await execute_image_team_flow(
        team=team,
        worker=DeterministicTeamWorker(),
        task=task,
        runtime=runtime,
    )
    if first != second:
        raise AssertionError("NODE-37 image team flow is not deterministic")
    if first.status != TeamTaskStatus.SUCCEEDED or first.final_result is None:
        raise AssertionError("NODE-37 image team flow did not succeed")
    if len(first.results) != 6:
        raise AssertionError("NODE-37 image team flow did not execute six specialists")
    critic = dict(first.results)["critic-agent"]
    if critic.artifacts:
        raise AssertionError("NODE-37 Critic wrote an artifact")
    if first.final_result.artifacts != (
        TeamArtifactRef("node37-image", "2", "image"),
    ):
        raise AssertionError("NODE-37 final edited artifact ref is incorrect")


async def _exercise_mock_provider(model_route: str) -> str:
    provider = MockProvider(model=model_route)
    request = ModelRequest(
        organization_id=UUID("00000000-0000-0000-0000-000000000037"),
        operation_id=UUID("00000000-0000-0000-0000-000000000137"),
        capability=Capability.LLM_REASONING,
        inputs={"prompt": "node37 deterministic provider probe"},
        trace_id="node37-provider-probe",
    )
    outcome = await provider.invoke(request)
    if outcome.status != ResultStatus.SUCCEEDED or not outcome.outputs:
        raise RuntimeError("NODE37_MOCK_PROVIDER_PROBE_FAILED")
    return (
        f"{provider.__class__.__module__}.{provider.__class__.__name__}:"
        f"{type(outcome).__name__}"
    )


def main() -> int:
    asyncio.run(main_async())
    print("NODE-37 Agent Team MockProvider E2E: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
