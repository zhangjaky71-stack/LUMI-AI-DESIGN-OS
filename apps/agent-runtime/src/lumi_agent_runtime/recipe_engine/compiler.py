from __future__ import annotations

from lumi_agent_runtime.agent_registry import AgentRegistry
from lumi_agent_runtime.skill_registry import SkillRegistry

from .atomic import AtomicStepCompiler
from .catalog import P0_DETERMINISTIC_SERVICES, P0_MEDIA_OPERATIONS
from .containers import ContainerCompiler
from .contracts import (
    CompiledRecipe,
    RecipeProvenance,
    StepType,
    TaskGraphTemplate,
    TaskTemplate,
)
from .registry import RecipeRegistry
from .resolution import CompileBindings, RecipeReferenceResolver
from .validation import (
    dependency_closure,
    topological_steps,
    validate_outputs,
    validate_step_references,
)


class RecipeCompiler:
    def __init__(
        self,
        *,
        recipes: RecipeRegistry,
        agents: AgentRegistry,
        skills: SkillRegistry,
        deterministic_services: frozenset[str] = P0_DETERMINISTIC_SERVICES,
        media_operations: frozenset[str] = P0_MEDIA_OPERATIONS,
    ) -> None:
        self.recipes = recipes
        resolver = RecipeReferenceResolver(
            agents=agents,
            skills=skills,
            recipes=recipes,
        )
        self.atomic = AtomicStepCompiler(
            resolver=resolver,
            deterministic_services=deterministic_services,
            media_operations=media_operations,
        )
        self.containers = ContainerCompiler(self.atomic)

    def compile(self, requested_ref: str) -> CompiledRecipe:
        resolved = self.recipes.resolve(requested_ref)
        definition = resolved.definition
        validate_outputs(definition)
        bindings = CompileBindings()
        tasks: list[TaskTemplate] = []
        for step in topological_steps(definition):
            sources = dependency_closure(step.step_id, definition)
            validate_step_references(step, definition, sources)
            if step.step_type == StepType.PARALLEL:
                tasks.extend(
                    self.containers.compile_parallel(
                        step,
                        definition=definition,
                        available_sources=sources,
                        bindings=bindings,
                    )
                )
            elif step.step_type == StepType.FOREACH:
                tasks.extend(
                    self.containers.compile_foreach(
                        step,
                        definition=definition,
                        available_sources=sources,
                        bindings=bindings,
                    )
                )
            else:
                tasks.append(
                    self.atomic.compile(
                        step,
                        task_key=step.step_id,
                        depends_on=step.depends_on,
                        budget_limit_usd=step.budget_limit_usd,
                        bindings=bindings,
                        current_recipe=definition,
                    )
                )
        graph = TaskGraphTemplate(
            recipe_id=definition.recipe_id,
            recipe_version=definition.version,
            tasks=tuple(tasks),
            recipe_budget_limit_usd=definition.budget_limit_usd,
            outputs=dict(definition.outputs),
            metadata={
                "recipe_definition_hash": definition.content_hash,
                "node33_contract": "TaskGraphTemplate:v1",
            },
        )
        provenance = RecipeProvenance(
            requested_ref=requested_ref,
            recipe_id=definition.recipe_id,
            exact_version=definition.version,
            recipe_definition_hash=definition.content_hash,
            release_manifest_revision=resolved.manifest_revision,
            agents=tuple(
                bindings.agents[key] for key in sorted(bindings.agents)
            ),
            skills=tuple(
                bindings.skills[key] for key in sorted(bindings.skills)
            ),
            subrecipes=tuple(
                bindings.subrecipes[key] for key in sorted(bindings.subrecipes)
            ),
            task_graph_template_hash=graph.content_hash,
        )
        return CompiledRecipe(
            definition=definition,
            task_graph=graph,
            provenance=provenance,
        )
