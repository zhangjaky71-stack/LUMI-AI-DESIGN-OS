from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from .contracts import (
    JoinPolicy,
    TaskDefinition,
    TaskGraphDefinition,
    TaskGraphEvent,
    TaskGraphSnapshot,
    TaskSnapshot,
    TaskState,
    TERMINAL_TASK_STATES,
)


def _task_snapshot(
    definition: TaskGraphDefinition,
    task: TaskDefinition,
    by_key: dict[str, TaskDefinition],
    *,
    now: datetime,
) -> TaskSnapshot:
    del by_key
    return TaskSnapshot(
        task_id=definition.task_id(task.task_key),
        graph_id=definition.graph_id,
        organization_id=definition.organization_id,
        project_id=definition.project_id,
        agent_run_id=definition.agent_run_id,
        task_key=task.task_key,
        kind=task.kind,
        objective=task.objective,
        status=TaskState.PENDING,
        depends_on=tuple(definition.task_id(key) for key in task.depends_on),
        dependency_keys=task.depends_on,
        priority=task.priority,
        retry=task.retry,
        budget_limit_usd=task.budget_limit_usd,
        concurrency_group=task.concurrency_group,
        concurrency_limit=task.concurrency_limit,
        join_policy=task.join_policy,
        agent_ref=task.agent_ref,
        context_bundle_ref=task.context_bundle_ref,
        input_refs=task.input_refs,
        metadata=dict(task.metadata),
        started_at=None,
        completed_at=None,
    )


def _join_decision(policy: JoinPolicy, dependencies: list[TaskSnapshot]) -> str:
    if not dependencies:
        return "ready"
    terminal = [task.status in TERMINAL_TASK_STATES for task in dependencies]
    success = [task.status is TaskState.SUCCEEDED for task in dependencies]
    if policy is JoinPolicy.ALL_SUCCESS:
        if all(success):
            return "ready"
        if all(terminal) and not all(success):
            return "impossible"
        if any(terminal[i] and not success[i] for i in range(len(dependencies))):
            return "impossible"
        return "pending"
    if policy is JoinPolicy.ALL_TERMINAL:
        return "ready" if all(terminal) else "pending"
    if any(success):
        return "ready"
    return "impossible" if all(terminal) else "pending"


def _event(
    task: TaskSnapshot,
    event_type: str,
    now: datetime,
    payload: dict[str, object],
) -> TaskGraphEvent:
    return TaskGraphEvent(
        event_type=event_type,
        graph_id=task.graph_id,
        organization_id=task.organization_id,
        project_id=task.project_id,
        agent_run_id=task.agent_run_id,
        task_id=task.task_id,
        occurred_at=now,
        payload={
            "task_key": task.task_key,
            "status": task.status.value,
            "logical_operation_key": task.logical_operation_key,
            **payload,
        },
    )


def _graph_event(
    graph: TaskGraphSnapshot,
    event_type: str,
    now: datetime,
    payload: dict[str, object],
) -> TaskGraphEvent:
    return TaskGraphEvent(
        event_type=event_type,
        graph_id=graph.graph_id,
        organization_id=graph.organization_id,
        project_id=graph.project_id,
        agent_run_id=graph.agent_run_id,
        occurred_at=now,
        payload={"status": graph.status.value, **payload},
    )


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _cost(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("TASK_COST_INVALID") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("TASK_COST_INVALID")
    return amount


def _worker(worker_id: str) -> None:
    if not worker_id or len(worker_id) > 255:
        raise ValueError("TASK_WORKER_ID_INVALID")


def _aware(value: datetime, code: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)
