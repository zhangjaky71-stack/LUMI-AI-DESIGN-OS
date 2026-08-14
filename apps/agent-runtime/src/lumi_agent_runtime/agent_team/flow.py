from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from lumi_agent_runtime.agent_registry.definition import AgentDefinition

from .contracts import TeamTaskInput, TeamTaskResult, TeamTaskStatus
from .delegation import DelegationRuntimeContext
from .handoff import build_handoff, result_to_payload, validate_result_for_agent
from .registry import CompiledAgentTeam


class TeamWorker(Protocol):
    async def execute(
        self,
        definition: AgentDefinition,
        task: TeamTaskInput,
    ) -> TeamTaskResult: ...


@dataclass(slots=True)
class AgentTeamFlowState:
    objective: str
    original_inputs: dict[str, Any]
    constraints: tuple[str, ...]
    expected_output: str
    results: dict[str, TeamTaskResult] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentTeamFlowOutcome:
    status: TeamTaskStatus
    summary: str
    results: tuple[tuple[str, TeamTaskResult], ...]
    final_result: TeamTaskResult | None


async def execute_image_team_flow(
    *,
    team: CompiledAgentTeam,
    worker: TeamWorker,
    task: TeamTaskInput,
    runtime: DelegationRuntimeContext,
) -> AgentTeamFlowOutcome:
    root = team.resolve(team.manifest.root_agent)
    state = AgentTeamFlowState(
        objective=task.objective,
        original_inputs=dict(task.inputs),
        constraints=task.constraints,
        expected_output=task.expected_output,
    )
    for child_id in team.manifest.image_flow:
        if child_id == root.agent_id:
            continue
        child = team.resolve(child_id)
        child_task = TeamTaskInput(
            objective=_child_objective(child_id, state),
            inputs={
                "original": state.original_inputs,
                "prior_results": {
                    agent_id: result_to_payload(result)
                    for agent_id, result in state.results.items()
                },
            },
            constraints=state.constraints,
            expected_output=f"TeamTaskResult from {child_id}",
            deadline_at=task.deadline_at,
            budget_remaining_usd=task.budget_remaining_usd,
            parent_task_id=task.parent_task_id,
            trace_id=task.trace_id,
        )
        handoff = build_handoff(
            parent=root,
            child=child,
            task=child_task,
            runtime=runtime,
        )
        result = await worker.execute(child, handoff.task)
        validate_result_for_agent(child, result)
        state.results[child_id] = result
        if result.status in {
            TeamTaskStatus.FAILED_FINAL,
            TeamTaskStatus.CANCELLED,
            TeamTaskStatus.WAITING_EXTERNAL,
            TeamTaskStatus.WAITING_APPROVAL,
        }:
            return AgentTeamFlowOutcome(
                status=result.status,
                summary=f"Image team flow stopped at {child_id}: {result.summary}",
                results=tuple(state.results.items()),
                final_result=result,
            )
        if result.status == TeamTaskStatus.FAILED_RETRYABLE:
            return AgentTeamFlowOutcome(
                status=TeamTaskStatus.FAILED_RETRYABLE,
                summary=f"Image team flow retry required at {child_id}: {result.summary}",
                results=tuple(state.results.items()),
                final_result=result,
            )

    final_result = state.results.get("image-editor") or state.results.get("image-generator")
    if final_result is None:
        return AgentTeamFlowOutcome(
            status=TeamTaskStatus.FAILED_FINAL,
            summary="Image team flow produced no generation/edit result",
            results=tuple(state.results.items()),
            final_result=None,
        )
    return AgentTeamFlowOutcome(
        status=TeamTaskStatus.SUCCEEDED,
        summary="Image team flow completed through bounded Creative Director handoffs",
        results=tuple(state.results.items()),
        final_result=final_result,
    )


def _child_objective(child_id: str, state: AgentTeamFlowState) -> str:
    stage = {
        "brand-strategist": "Derive source-backed brand constraints for the objective.",
        "research-agent": "Find source-backed evidence relevant to the objective and brand constraints.",
        "prompt-engineer": "Translate the approved objective, constraints, and evidence into a generation spec.",
        "image-generator": "Generate the requested image from the approved generation spec.",
        "critic-agent": "Critique the generated candidate against the brief and constraints without writing.",
        "image-editor": "Apply only the approved corrective edits identified by the brief and critique.",
    }.get(child_id, f"Execute the assigned {child_id} specialist stage.")
    return f"{stage} Overall objective: {state.objective}"
