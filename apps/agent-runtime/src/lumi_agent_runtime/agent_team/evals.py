from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .catalog import CANONICAL_AGENT_IDS
from .contracts import TeamRoleDefinition

CORE_50_AGENT_IDS = frozenset(
    {
        "brief-agent",
        "research-agent",
        "layout-agent",
        "image-edit-agent",
        "critic-agent",
    }
)


@dataclass(frozen=True, slots=True)
class RoleEvalCase:
    case_id: str
    agent_id: str
    focus: str


@dataclass(frozen=True, slots=True)
class RoleEvalProfile:
    agent_id: str
    minimum_cases: int
    cases: tuple[RoleEvalCase, ...]

    def __post_init__(self) -> None:
        if len(self.cases) < self.minimum_cases:
            raise ValueError("AGENT_TEAM_EVAL_CASE_COUNT_TOO_SMALL")
        if any(case.agent_id != self.agent_id for case in self.cases):
            raise ValueError("AGENT_TEAM_EVAL_AGENT_MISMATCH")


def build_eval_profiles(
    roles: Mapping[str, TeamRoleDefinition],
) -> Mapping[str, RoleEvalProfile]:
    if tuple(roles) != CANONICAL_AGENT_IDS:
        raise ValueError("AGENT_TEAM_EVAL_CANONICAL_TEAM_REQUIRED")
    profiles: dict[str, RoleEvalProfile] = {}
    focuses = (
        "role-boundary",
        "structured-handoff",
        "tool-minimization",
        "prompt-injection-resistance",
        "citation-discipline",
        "constraint-preservation",
        "approval-gating",
        "failure-reporting",
        "confidence-calibration",
        "provenance-preservation",
    )
    for agent_id in CANONICAL_AGENT_IDS:
        count = 50 if agent_id in CORE_50_AGENT_IDS else 20
        cases = tuple(
            RoleEvalCase(
                case_id=f"{agent_id}-smoke-{index + 1:02d}",
                agent_id=agent_id,
                focus=focuses[index % len(focuses)],
            )
            for index in range(count)
        )
        profiles[agent_id] = RoleEvalProfile(
            agent_id=agent_id,
            minimum_cases=count,
            cases=cases,
        )
    return profiles
