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
    task_ids = {task.task_key: uuid5(graph_id, task.task_key) for task in compiled.task_graph.tasks}
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
            template.metadata, "foreach_group"
        )
        tasks.append(
            TaskSnapshot(
                task_id=task_ids[template.task_key],
                graph_id=graph_id,
                organization_id=organization_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
                task_key=template.task_key,
                recipe_step_id=template.recipe_step_id,
                step_type=template.step_type.value,
                owner=template.owner,
                status=TaskState.READY if not dependencies else TaskState.PENDING,
                depends_on=dependencies,
                input_bindings=dict(template.input_bindings),
                output_schema=template.output_schema,
                budget_limit_usd=template.budget_limit_usd,
                concurrency_group=group,
                concurrency_limit=_integer(template.metadata, "max_parallel"),
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


def _integer(metadata: dict[str, object], key: str) -> int | None:
    value = metadata.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
