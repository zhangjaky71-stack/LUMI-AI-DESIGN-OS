from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .catalog import DEFAULT_TEAM
from .contracts import TeamRoleDefinition
from .handoff import validate_review_separation


class PosterFlowStage(StrEnum):
    BRIEF = "brief"
    RESEARCH = "research"
    CREATIVE_DIRECTION = "creative_direction"
    APPROVAL = "approval"
    PRODUCTION = "production"
    REVIEW = "review"
    REPAIR = "repair"
    EXPORT = "export"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class FlowStep:
    stage: PosterFlowStage
    agents: tuple[str, ...]
    parallel: bool = False
    approval_required: bool = False


@dataclass(frozen=True, slots=True)
class PosterFlowPlan:
    steps: tuple[FlowStep, ...]

    def __post_init__(self) -> None:
        if not self.steps or self.steps[-1].stage is not PosterFlowStage.COMPLETE:
            raise ValueError("AGENT_TEAM_FLOW_MUST_COMPLETE")
        stages = tuple(step.stage for step in self.steps)
        required = (
            PosterFlowStage.BRIEF,
            PosterFlowStage.RESEARCH,
            PosterFlowStage.CREATIVE_DIRECTION,
            PosterFlowStage.APPROVAL,
            PosterFlowStage.PRODUCTION,
            PosterFlowStage.REVIEW,
            PosterFlowStage.REPAIR,
            PosterFlowStage.EXPORT,
            PosterFlowStage.COMPLETE,
        )
        if stages != required:
            raise ValueError("AGENT_TEAM_FLOW_STAGE_ORDER_INVALID")


def build_coffee_poster_mock_plan(
    roles: Mapping[str, TeamRoleDefinition] = DEFAULT_TEAM,
) -> PosterFlowPlan:
    production = (
        "copywriting-agent",
        "typography-agent",
        "layout-agent",
        "image-agent",
    )
    reviewers = (
        "critic-agent",
        "brand-consistency-agent",
        "identity-agent",
    )
    for producer in ("image-agent",):
        for reviewer in reviewers:
            validate_review_separation(
                producer_agent_id=producer,
                reviewer_agent_id=reviewer,
                roles=roles,
            )
    return PosterFlowPlan(
        steps=(
            FlowStep(PosterFlowStage.BRIEF, ("brief-agent",)),
            FlowStep(PosterFlowStage.RESEARCH, ("research-agent", "brand-strategy-agent"), parallel=True),
            FlowStep(PosterFlowStage.CREATIVE_DIRECTION, ("creative-director", "moodboard-agent"), parallel=True),
            FlowStep(PosterFlowStage.APPROVAL, ("director",), approval_required=True),
            FlowStep(PosterFlowStage.PRODUCTION, production, parallel=True),
            FlowStep(PosterFlowStage.REVIEW, reviewers, parallel=True),
            FlowStep(PosterFlowStage.REPAIR, ("image-edit-agent", "layout-agent"), parallel=True),
            FlowStep(PosterFlowStage.EXPORT, ("export-agent",)),
            FlowStep(PosterFlowStage.COMPLETE, ("director",)),
        )
    )
