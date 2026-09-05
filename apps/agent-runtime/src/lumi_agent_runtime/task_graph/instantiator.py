from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4, uuid5

from lumi_agent_runtime.recipe_engine import CompiledRecipe

from .graph_contracts import TaskGraphProvenance, TaskGraphSnapshot
from .states import TaskGraphState, TaskState
from .task_contracts import TaskSnapshot


@dataclass(frozen=True, slots=True)
class InstantiatedTaskGraph:
    graph: TaskGraphSnapshot
    tasks: tuple[TaskSnapshot, ...]


def instantiate_compiled_recipe(
    compiled: CompiledRecipe,
    *,
    organization_id: UUID,
    project_id: UUID,
    agent_run_id: UUID,
    graph_id: UUID | None = None,
) -> InstantiatedTaskGraph:
    graph_id = graph_id or uuid4()
    task_ids = {
        task.task_key: uuid5(graph_id, f"task:{task.task_key}")
        for task in compiled.task_graph.tasks
    }
    provenance = TaskGraphProvenance(
        recipe_id=compiled.definition.recipe_id,
        recipe_version=compiled.definition.version,
        recipe_definition_hash=compiled.definition.content_hash,
        recipe_provenance_hash=compiled.provenance.freeze_hash,
        task_graph_template_hash=compiled.task_graph.content_hash,
    )
    tasks: list[TaskSnapshot] = []
    for template in compiled.task_graph.tasks:
        dependencies = tuple(task_ids[key] for key in template.depends_on)
        group = _text(template.metadata, "parallel_group") or _text(
            template.metadata,
            "foreach_group",
        )
        tasks.append(
            TaskSnapshot(
                task_id=task_ids[template.task_key],
                graph_id=graph_id,
                organization_id=organization_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
                parent_task_id=None,
                task_key=template.task_key,
                recipe_step_id=template.recipe_step_id,
                step_type=template.step_type.value,
                owner=template.owner,
                status=TaskState.READY if not dependencies else TaskState.PENDING,
                depends_on=dependencies,
                input_bindings=dict(template.input_bindings),
                output_schema=template.output_schema,
                priority=_bounded_integer(template.metadata, "priority", 0, 1000) or 100,
                max_attempts=_bounded_integer(template.metadata, "max_attempts", 1, 20) or 3,
                budget_limit_usd=template.budget_limit_usd,
                dynamic_child_limit=(
                    _bounded_integer(template.metadata, "dynamic_child_limit", 0, 32) or 0
                ),
                concurrency_group=group,
                concurrency_limit=_concurrency_limit(template.metadata, group),
                condition=template.condition,
                metadata=dict(template.metadata),
            )
        )
    graph = TaskGraphSnapshot(
        graph_id=graph_id,
        organization_id=organization_id,
        project_id=project_id,
        agent_run_id=agent_run_id,
        provenance=provenance,
        status=TaskGraphState.RUNNING,
        recipe_budget_limit_usd=compiled.task_graph.recipe_budget_limit_usd,
        task_count=len(tasks),
    )
    return InstantiatedTaskGraph(graph=graph, tasks=tuple(tasks))


def _text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _bounded_integer(
    metadata: dict[str, object],
    key: str,
    minimum: int,
    maximum: int,
) -> int | None:
    value = metadata.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum:
        return value
    return None


def _concurrency_limit(metadata: dict[str, object], group: str | None) -> int | None:
    if group is None:
        return None
    explicit = _bounded_integer(metadata, "max_parallel", 1, 32)
    if explicit is not None:
        return explicit
    foreach_count = _bounded_integer(metadata, "foreach_count", 1, 8)
    return min(foreach_count, 4) if foreach_count is not None else None
