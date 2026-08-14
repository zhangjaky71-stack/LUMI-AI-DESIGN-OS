from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid5

from .errors import TaskGraphBudgetError, TaskGraphExpansionError
from .events import TaskGraphEvent
from .memory_store import InMemoryTaskGraphStore
from .states import TaskState
from .task_contracts import TaskSnapshot


def expand_dynamic_task(
    store: InMemoryTaskGraphStore,
    parent_task_id: UUID,
    *,
    child_key: str,
    owner: str,
    step_type: str,
    output_schema: str,
    budget_limit_usd: str | None = None,
    concurrency_group: str | None = None,
    concurrency_limit: int | None = None,
    dynamic_child_limit: int = 0,
) -> TaskSnapshot:
    parent = store.task(parent_task_id)
    if parent.status != TaskState.RUNNING:
        raise TaskGraphExpansionError("TASK_DYNAMIC_PARENT_MUST_BE_RUNNING")
    if parent.dynamic_child_limit < 1:
        raise TaskGraphExpansionError("TASK_DYNAMIC_EXPANSION_NOT_ALLOWED")
    if parent.dynamic_depth >= 4:
        raise TaskGraphExpansionError("TASK_DYNAMIC_DEPTH_LIMIT")
    siblings = [
        item
        for item in store.tasks(parent.graph_id)
        if item.parent_task_id == parent.task_id
    ]
    if len(siblings) >= parent.dynamic_child_limit:
        raise TaskGraphExpansionError("TASK_DYNAMIC_CHILD_LIMIT")
    if budget_limit_usd is not None and parent.budget_limit_usd is not None:
        if Decimal(budget_limit_usd) > Decimal(parent.budget_limit_usd):
            raise TaskGraphBudgetError("TASK_DYNAMIC_BUDGET_ESCALATION")
    if (
        concurrency_limit is not None
        and parent.concurrency_limit is not None
        and concurrency_limit > parent.concurrency_limit
    ):
        raise TaskGraphExpansionError("TASK_DYNAMIC_CONCURRENCY_ESCALATION")
    if dynamic_child_limit > parent.dynamic_child_limit:
        raise TaskGraphExpansionError("TASK_DYNAMIC_CHILD_SCOPE_ESCALATION")
    task_id = uuid5(parent.graph_id, f"dynamic:{parent.task_id}:{child_key}")
    child = TaskSnapshot(
        task_id=task_id,
        graph_id=parent.graph_id,
        organization_id=parent.organization_id,
        project_id=parent.project_id,
        agent_run_id=parent.agent_run_id,
        parent_task_id=parent.task_id,
        task_key=f"{parent.task_key}.{child_key}",
        recipe_step_id=parent.recipe_step_id,
        step_type=step_type,
        owner=owner,
        status=TaskState.READY,
        depends_on=(),
        input_bindings={},
        output_schema=output_schema,
        budget_limit_usd=budget_limit_usd,
        dynamic_depth=parent.dynamic_depth + 1,
        dynamic_child_limit=dynamic_child_limit,
        concurrency_group=concurrency_group or parent.concurrency_group,
        concurrency_limit=concurrency_limit or parent.concurrency_limit,
        metadata={"dynamic": True},
    )
    store.add_dynamic_task(child)
    graph = store.graph(parent.graph_id)
    store.replace_graph(
        replace(
            graph,
            task_count=graph.task_count + 1,
            state_version=graph.state_version + 1,
        ),
        expected_version=graph.state_version,
    )
    store.emit(
        TaskGraphEvent(
            event_name="task.dynamic_created",
            graph_id=parent.graph_id,
            task_id=child.task_id,
            organization_id=parent.organization_id,
            payload={
                "task_key": child.task_key,
                "parent_task_id": str(parent.task_id),
                "dynamic_depth": child.dynamic_depth,
            },
        )
    )
    return child
