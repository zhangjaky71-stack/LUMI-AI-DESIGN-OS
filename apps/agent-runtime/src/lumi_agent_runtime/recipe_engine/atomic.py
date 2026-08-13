from __future__ import annotations

from .catalog import P0_DETERMINISTIC_SERVICES, P0_MEDIA_OPERATIONS
from .contracts import ApprovalPolicy, RecipeDefinition, RecipeStep, StepType, TaskTemplate
from .errors import RecipeCompileError
from .resolution import CompileBindings, RecipeReferenceResolver


class AtomicStepCompiler:
    def __init__(
        self,
        *,
        resolver: RecipeReferenceResolver,
        deterministic_services: frozenset[str] = P0_DETERMINISTIC_SERVICES,
        media_operations: frozenset[str] = P0_MEDIA_OPERATIONS,
    ) -> None:
        self.resolver = resolver
        self.deterministic_services = deterministic_services
        self.media_operations = media_operations

    def compile(
        self,
        step: RecipeStep,
        *,
        task_key: str,
        depends_on: tuple[str, ...],
        budget_limit_usd: str | None,
        bindings: CompileBindings,
        current_recipe: RecipeDefinition,
        extra_metadata: dict[str, object] | None = None,
    ) -> TaskTemplate:
        metadata: dict[str, object] = dict(extra_metadata or {})
        owner: str
        if step.step_type == StepType.AGENT:
            owner, agent_metadata = self.resolver.bind_agent(step, bindings)
            metadata.update(agent_metadata)
        elif step.step_type in {StepType.DETERMINISTIC, StepType.FINALIZE}:
            if step.service_key not in self.deterministic_services:
                raise RecipeCompileError(
                    f"unregistered deterministic service: {step.service_key}"
                )
            owner = f"DETERMINISTIC_SERVICE:{step.service_key}"
        elif step.step_type == StepType.MEDIA_JOB:
            if step.media_operation not in self.media_operations:
                raise RecipeCompileError(
                    f"unregistered media operation: {step.media_operation}"
                )
            owner = "MEDIA_WORKER"
            metadata["media_operation"] = step.media_operation
        elif step.step_type == StepType.APPROVAL:
            if step.approval is None:
                raise RecipeCompileError("APPROVAL step has no policy")
            owner = "HUMAN"
            metadata.update(_approval_metadata(step.approval))
        elif step.step_type == StepType.QUALITY_GATE:
            if step.quality_gate is None:
                raise RecipeCompileError("QUALITY_GATE step has no policy")
            owner = "DETERMINISTIC_SERVICE:quality.evaluate"
            quality = step.quality_gate
            repair_exact = None
            if quality.repair_recipe is not None:
                repair_exact, _ = self.resolver.bind_subrecipe(
                    quality.repair_recipe,
                    current_recipe=current_recipe,
                    bindings=bindings,
                )
            metadata.update(
                {
                    "metrics": list(quality.metrics),
                    "thresholds": quality.thresholds,
                    "repair_recipe": repair_exact,
                    "max_repair_iterations": quality.max_repair_iterations,
                }
            )
        elif step.step_type == StepType.SUBRECIPE:
            if step.recipe_ref is None:
                raise RecipeCompileError("SUBRECIPE step has no Recipe reference")
            exact, content_hash = self.resolver.bind_subrecipe(
                step.recipe_ref,
                current_recipe=current_recipe,
                bindings=bindings,
            )
            owner = f"RECIPE:{exact}"
            metadata.update(
                {
                    "requested_recipe_ref": step.recipe_ref,
                    "recipe_definition_hash": content_hash,
                }
            )
        else:
            raise RecipeCompileError(
                f"atomic compiler does not support {step.step_type.value}"
            )
        if step.loop is not None:
            metadata["loop"] = {
                "max_iterations": step.loop.max_iterations,
                "budget_limit_usd": step.loop.budget_limit_usd,
                "stop_condition": step.loop.stop_condition,
            }
        return TaskTemplate(
            task_key=task_key,
            recipe_step_id=step.step_id,
            step_type=step.step_type,
            owner=owner,
            depends_on=depends_on,
            input_bindings=dict(step.input_bindings),
            output_schema=step.output_schema,
            condition=step.condition,
            budget_limit_usd=budget_limit_usd,
            metadata=metadata,
        )


def _approval_metadata(policy: ApprovalPolicy) -> dict[str, object]:
    return {
        "approval": {
            "prompt_summary": policy.prompt_summary,
            "allowed_actions": list(policy.allowed_actions),
            "artifact_refs": list(policy.artifact_refs),
            "option_refs": list(policy.option_refs),
            "expiry_seconds": policy.expiry_seconds,
            "resume_mapping": dict(policy.resume_mapping),
            "interrupt_hook": "NODE-28:approval_interrupt",
            "decision_authority": "LUMI_APPROVAL_SERVICE",
        }
    }
