from __future__ import annotations

from decimal import Decimal

from .atomic import AtomicStepCompiler
from .contracts import JoinPolicy, RecipeDefinition, RecipeStep, StepType, TaskTemplate
from .errors import RecipeBudgetError, RecipeCompileError
from .resolution import CompileBindings
from .validation import validate_step_references

_ATOMIC_CHILD_TYPES = frozenset(
    {
        StepType.AGENT,
        StepType.DETERMINISTIC,
        StepType.MEDIA_JOB,
    }
)


class ContainerCompiler:
    def __init__(self, atomic: AtomicStepCompiler) -> None:
        self.atomic = atomic

    def compile_parallel(
        self,
        step: RecipeStep,
        *,
        definition: RecipeDefinition,
        available_sources: frozenset[str],
        bindings: CompileBindings,
    ) -> tuple[TaskTemplate, ...]:
        if step.condition is not None:
            raise RecipeCompileError("parallel container condition is unsupported in V1")
        policy = step.parallel
        if policy is None:
            raise RecipeCompileError("parallel policy missing")
        if policy.budget_limit_usd is None or not policy.budget_split:
            raise RecipeBudgetError(
                "parallel requires total budget and explicit budget split"
            )
        if len(policy.budget_split) != len(step.children):
            raise RecipeBudgetError("parallel budget split count differs from children")
        if sum(Decimal(item) for item in policy.budget_split) != Decimal(
            policy.budget_limit_usd
        ):
            raise RecipeBudgetError("parallel budget split must equal total budget")
        if policy.join_policy == JoinPolicy.MIN_SUCCESS:
            if policy.min_success is None or policy.min_success > len(step.children):
                raise RecipeCompileError("parallel MIN_SUCCESS is outside child count")

        tasks: list[TaskTemplate] = []
        child_keys: list[str] = []
        for index, child in enumerate(step.children):
            if child.step_type not in _ATOMIC_CHILD_TYPES or child.depends_on:
                raise RecipeCompileError(
                    "parallel V1 children must be atomic and have no local dependencies"
                )
            validate_step_references(child, definition, available_sources)
            key = f"{step.step_id}.{child.step_id}"
            child_keys.append(key)
            tasks.append(
                self.atomic.compile(
                    child,
                    task_key=key,
                    depends_on=step.depends_on,
                    budget_limit_usd=policy.budget_split[index],
                    bindings=bindings,
                    current_recipe=definition,
                    extra_metadata={
                        "parallel_group": step.step_id,
                        "parallel_index": index,
                        "max_parallel": policy.max_parallel,
                    },
                )
            )
        tasks.append(
            TaskTemplate(
                task_key=step.step_id,
                recipe_step_id=step.step_id,
                step_type=StepType.PARALLEL,
                owner="JOIN",
                depends_on=tuple(child_keys),
                input_bindings={},
                output_schema=step.output_schema,
                budget_limit_usd=policy.budget_limit_usd,
                metadata={
                    "join_policy": policy.join_policy.value,
                    "min_success": policy.min_success,
                    "max_parallel": policy.max_parallel,
                    "budget_split": list(policy.budget_split),
                },
            )
        )
        return tuple(tasks)

    def compile_foreach(
        self,
        step: RecipeStep,
        *,
        definition: RecipeDefinition,
        available_sources: frozenset[str],
        bindings: CompileBindings,
    ) -> tuple[TaskTemplate, ...]:
        if step.condition is not None:
            raise RecipeCompileError("foreach container condition is unsupported in V1")
        if step.foreach_count is None or step.template is None:
            raise RecipeCompileError("foreach count/template missing")
        template = step.template
        if template.step_type not in _ATOMIC_CHILD_TYPES or template.depends_on:
            raise RecipeCompileError(
                "foreach V1 template must be atomic and have no local dependencies"
            )
        validate_step_references(template, definition, available_sources)
        per_item_budget = None
        if step.budget_limit_usd is not None:
            per_item_budget = _divide_budget(step.budget_limit_usd, step.foreach_count)
        tasks: list[TaskTemplate] = []
        child_keys: list[str] = []
        for index in range(step.foreach_count):
            key = f"{step.step_id}[{index}]"
            child_keys.append(key)
            tasks.append(
                self.atomic.compile(
                    template,
                    task_key=key,
                    depends_on=step.depends_on,
                    budget_limit_usd=per_item_budget or template.budget_limit_usd,
                    bindings=bindings,
                    current_recipe=definition,
                    extra_metadata={
                        "foreach_group": step.step_id,
                        "foreach_index": index,
                        "foreach_count": step.foreach_count,
                    },
                )
            )
        tasks.append(
            TaskTemplate(
                task_key=step.step_id,
                recipe_step_id=step.step_id,
                step_type=StepType.FOREACH,
                owner="JOIN",
                depends_on=tuple(child_keys),
                input_bindings={},
                output_schema=step.output_schema,
                budget_limit_usd=step.budget_limit_usd,
                metadata={
                    "join_policy": JoinPolicy.ALL.value,
                    "foreach_count": step.foreach_count,
                    "max_parallel": min(step.foreach_count, 4),
                    "per_item_budget_usd": per_item_budget,
                },
            )
        )
        return tuple(tasks)


def _divide_budget(total: str, count: int) -> str:
    return format(Decimal(total) / Decimal(count), "f")
