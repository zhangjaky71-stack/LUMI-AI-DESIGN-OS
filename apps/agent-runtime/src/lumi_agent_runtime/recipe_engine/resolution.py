from __future__ import annotations

from dataclasses import dataclass, field

from lumi_agent_runtime.agent_registry import AgentRegistry
from lumi_agent_runtime.skill_registry import SkillRegistry

from .contracts import (
    RecipeDefinition,
    RecipeStep,
    ResolvedAgentBinding,
    ResolvedSkillBinding,
)
from .errors import RecipeCompileError
from .registry import RecipeRegistry


@dataclass(slots=True)
class CompileBindings:
    agents: dict[str, ResolvedAgentBinding] = field(default_factory=dict)
    skills: dict[str, ResolvedSkillBinding] = field(default_factory=dict)
    subrecipes: dict[str, str] = field(default_factory=dict)


class RecipeReferenceResolver:
    def __init__(
        self,
        *,
        agents: AgentRegistry,
        skills: SkillRegistry,
        recipes: RecipeRegistry,
    ) -> None:
        self.agents = agents
        self.skills = skills
        self.recipes = recipes

    def bind_agent(
        self,
        step: RecipeStep,
        bindings: CompileBindings,
    ) -> tuple[str, dict[str, object]]:
        if step.agent_ref is None:
            raise RecipeCompileError("AGENT step has no Agent reference")
        resolved_agent = self.agents.resolve(step.agent_ref)
        identity = (
            f"{resolved_agent.definition.agent_id}@"
            f"{resolved_agent.definition.version}"
        )
        bindings.agents.setdefault(
            identity,
            ResolvedAgentBinding(
                requested_ref=step.agent_ref,
                agent_id=resolved_agent.definition.agent_id,
                exact_version=resolved_agent.definition.version,
                definition_hash=resolved_agent.definition.content_hash,
                provenance_hash=resolved_agent.provenance.freeze_hash,
            ),
        )
        declared_skills = {
            item.skill_id: item
            for item in resolved_agent.definition.skills
        }
        dependency_skills = {
            item.key: item
            for item in resolved_agent.provenance.dependencies
            if item.kind == "skill"
        }
        for dependency in dependency_skills.values():
            resolved_skill = self.skills.resolve(
                f"{dependency.key}@{dependency.exact_version}"
            )
            bindings.skills.setdefault(
                resolved_skill.definition.identity,
                ResolvedSkillBinding(
                    requested_ref=dependency.requested,
                    skill_id=dependency.key,
                    exact_version=dependency.exact_version,
                    content_hash=(
                        dependency.content_hash
                        or resolved_skill.definition.content_hash
                    ),
                ),
            )
        explicit_skills: list[str] = []
        for requested_skill in step.skill_refs:
            resolved_skill = self.skills.resolve(requested_skill)
            skill_id = resolved_skill.definition.skill_id
            if skill_id not in declared_skills or skill_id not in dependency_skills:
                raise RecipeCompileError(
                    f"Recipe Skill expands Agent definition: {requested_skill}"
                )
            dependency = dependency_skills[skill_id]
            if dependency.exact_version != resolved_skill.definition.version:
                raise RecipeCompileError(
                    "Recipe Skill exact version differs from Agent freeze: "
                    f"{requested_skill}"
                )
            explicit_skills.append(resolved_skill.definition.identity)
        return (
            f"AGENT:{identity}",
            {
                "requested_agent_ref": step.agent_ref,
                "agent_definition_hash": resolved_agent.definition.content_hash,
                "agent_provenance_hash": resolved_agent.provenance.freeze_hash,
                "skill_refs": explicit_skills,
            },
        )

    def bind_subrecipe(
        self,
        requested_ref: str,
        *,
        current_recipe: RecipeDefinition,
        bindings: CompileBindings,
    ) -> tuple[str, str]:
        resolved = self.recipes.resolve(requested_ref)
        if resolved.definition.identity == current_recipe.identity:
            raise RecipeCompileError("Recipe cannot directly recurse into itself")
        exact = resolved.definition.identity
        bindings.subrecipes[exact] = exact
        return exact, resolved.definition.content_hash
