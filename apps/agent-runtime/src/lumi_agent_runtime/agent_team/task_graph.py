from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .registry import CompiledAgentTeam


@dataclass(frozen=True, slots=True)
class TeamGraphStep:
    step_id: str
    agent_id: str
    depends_on: tuple[str, ...]
    writes_artifact_slot: str | None = None

    def __post_init__(self) -> None:
        if not self.step_id or not self.agent_id:
            raise ValueError("AGENT_TEAM_GRAPH_STEP_INVALID")
        if self.step_id in self.depends_on:
            raise ValueError("AGENT_TEAM_GRAPH_SELF_DEPENDENCY")

    @property
    def owner_key(self) -> str:
        return f"AGENT:{self.agent_id}@2.0.0"


@dataclass(frozen=True, slots=True)
class TeamTaskGraphPlan:
    graph_key: str
    steps: tuple[TeamGraphStep, ...]

    def __post_init__(self) -> None:
        if not self.graph_key or len(self.steps) < 4:
            raise ValueError("AGENT_TEAM_GRAPH_TOO_SMALL")
        _validate_dag(self.steps)
        _validate_write_serialization(self.steps)

    def as_task_graph_template(self) -> dict[str, Any]:
        """Provider-neutral NODE-33 adapter payload; scheduling remains TaskGraph-owned."""
        return {
            "graph_key": self.graph_key,
            "steps": [
                {
                    "step_id": step.step_id,
                    "owner": step.owner_key,
                    "depends_on": list(step.depends_on),
                    "task_type": "AGENT_TEAM_HANDOFF",
                    "writes_artifact_slot": step.writes_artifact_slot,
                }
                for step in self.steps
            ],
        }


def image_team_task_graph(team: CompiledAgentTeam) -> TeamTaskGraphPlan:
    required = {
        "brand-strategist",
        "research-agent",
        "prompt-engineer",
        "image-generator",
        "critic-agent",
        "image-editor",
    }
    if not required <= set(team.definitions):
        raise ValueError("AGENT_TEAM_IMAGE_GRAPH_ROLE_MISSING")
    return TeamTaskGraphPlan(
        graph_key="agent-team-image-v1",
        steps=(
            TeamGraphStep("brand", "brand-strategist", ()),
            TeamGraphStep("research", "research-agent", ("brand",)),
            TeamGraphStep("prompt", "prompt-engineer", ("brand", "research")),
            TeamGraphStep(
                "generate",
                "image-generator",
                ("prompt",),
                writes_artifact_slot="image-candidate",
            ),
            TeamGraphStep("critic", "critic-agent", ("generate",)),
            TeamGraphStep(
                "edit",
                "image-editor",
                ("generate", "critic"),
                writes_artifact_slot="image-final",
            ),
        ),
    )


def _validate_dag(steps: tuple[TeamGraphStep, ...]) -> None:
    by_id = {step.step_id: step for step in steps}
    if len(by_id) != len(steps):
        raise ValueError("AGENT_TEAM_GRAPH_DUPLICATE_STEP")
    for step in steps:
        unknown = set(step.depends_on) - set(by_id)
        if unknown:
            raise ValueError("AGENT_TEAM_GRAPH_UNKNOWN_DEPENDENCY")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            raise ValueError("AGENT_TEAM_GRAPH_CYCLE")
        visiting.add(step_id)
        for dependency in by_id[step_id].depends_on:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step in steps:
        visit(step.step_id)


def _validate_write_serialization(steps: tuple[TeamGraphStep, ...]) -> None:
    writers = [step for step in steps if step.writes_artifact_slot is not None]
    by_id = {step.step_id: step for step in steps}

    def ancestors(step_id: str) -> set[str]:
        output: set[str] = set()
        stack = list(by_id[step_id].depends_on)
        while stack:
            current = stack.pop()
            if current in output:
                continue
            output.add(current)
            stack.extend(by_id[current].depends_on)
        return output

    ancestor_map = {step.step_id: ancestors(step.step_id) for step in writers}
    for index, left in enumerate(writers):
        for right in writers[index + 1 :]:
            if left.writes_artifact_slot != right.writes_artifact_slot:
                continue
            ordered = (
                left.step_id in ancestor_map[right.step_id]
                or right.step_id in ancestor_map[left.step_id]
            )
            if not ordered:
                raise ValueError("AGENT_TEAM_GRAPH_CONCURRENT_ARTIFACT_WRITE")
