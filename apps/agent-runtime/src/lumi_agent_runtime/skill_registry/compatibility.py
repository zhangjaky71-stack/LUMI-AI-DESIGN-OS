from __future__ import annotations

from dataclasses import dataclass

from lumi_agent_runtime.agent_registry.definition import AgentDefinition

from .errors import (
    SkillCapabilityError,
    SkillCompatibilityError,
    SkillPermissionError,
)
from .registry import SkillRegistry


@dataclass(frozen=True, slots=True)
class AgentSkillCompatibilityValidator:
    registry: SkillRegistry
    available_capabilities: frozenset[str]

    def validate(self, definition: AgentDefinition) -> None:
        allowed_tools = frozenset(item.name for item in definition.tools)
        granted_permissions = frozenset(
            key for key, enabled in definition.permissions.items() if enabled
        )
        for requirement in definition.skills:
            skill = self.registry.resolve(requirement.ref).definition
            if definition.agent_id not in skill.compatible_agents:
                raise SkillCompatibilityError(
                    f"Agent {definition.agent_id} cannot use {skill.identity}"
                )
            missing_tools = {
                item.name for item in skill.required_tools
            } - allowed_tools
            missing_permissions = set(skill.permissions) - granted_permissions
            missing_capabilities = (
                set(skill.required_capabilities) - self.available_capabilities
            )
            if missing_tools or missing_permissions:
                raise SkillPermissionError(
                    "Skill expands Agent scope: "
                    f"tools={sorted(missing_tools)}, "
                    f"permissions={sorted(missing_permissions)}"
                )
            if missing_capabilities:
                raise SkillCapabilityError(
                    "Agent model policy lacks Skill capabilities: "
                    f"{sorted(missing_capabilities)}"
                )
