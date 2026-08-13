from __future__ import annotations

from dataclasses import dataclass

from .contracts import ResolvedSkillPack, SkillExecutionContext, SkillReleaseStatus
from .errors import SkillSelectionError
from .registry import SkillRegistry


@dataclass(frozen=True, slots=True)
class SkillSelectionContext:
    task_type: str
    execution: SkillExecutionContext


class SkillSelector:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def select(self, context: SkillSelectionContext) -> ResolvedSkillPack:
        candidates = [
            definition
            for definition in self.registry.definitions()
            if context.task_type in definition.task_types
            and context.execution.agent_id in definition.compatible_agents
            and bool(definition.metadata.get("selector_primary", False))
            and self.registry.resolve(
                f"{definition.skill_id}@{definition.version}"
            ).release_status
            == SkillReleaseStatus.PRODUCTION
        ]
        if len(candidates) != 1:
            raise SkillSelectionError(
                "expected one primary Skill for "
                f"{context.task_type}/{context.execution.agent_id}, got {len(candidates)}"
            )
        root = candidates[0]
        return self.registry.resolve_pack(
            (f"{root.skill_id}@{root.version}",),
            context.execution,
        )
