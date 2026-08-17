from __future__ import annotations

from .contracts import TaskGraphState, TaskState
from .errors import TaskGraphStateError

_TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PENDING: frozenset({TaskState.READY, TaskState.CANCELLED, TaskState.SKIPPED}),
    TaskState.READY: frozenset({TaskState.RUNNING, TaskState.CANCELLED, TaskState.SKIPPED}),
    TaskState.RUNNING: frozenset(
        {
            TaskState.SUCCEEDED,
            TaskState.FAILED_RETRYABLE,
            TaskState.FAILED_FINAL,
            TaskState.WAITING_USER,
            TaskState.WAITING_EXTERNAL,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_USER: frozenset({TaskState.READY, TaskState.SUCCEEDED, TaskState.CANCELLED}),
    TaskState.WAITING_EXTERNAL: frozenset(
        {TaskState.READY, TaskState.SUCCEEDED, TaskState.FAILED_FINAL, TaskState.CANCELLED}
    ),
    TaskState.FAILED_RETRYABLE: frozenset(
        {TaskState.READY, TaskState.FAILED_FINAL, TaskState.CANCELLED}
    ),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED_FINAL: frozenset(),
    TaskState.CANCELLED: frozenset(),
    TaskState.SKIPPED: frozenset(),
}

_GRAPH_TRANSITIONS: dict[TaskGraphState, frozenset[TaskGraphState]] = {
    TaskGraphState.RUNNING: frozenset(
        {
            TaskGraphState.PAUSED,
            TaskGraphState.WAITING,
            TaskGraphState.FAILURE_DRAINING,
            TaskGraphState.CANCEL_REQUESTED,
            TaskGraphState.SUCCEEDED,
            TaskGraphState.FAILED_FINAL,
            TaskGraphState.CANCELLED,
        }
    ),
    TaskGraphState.PAUSED: frozenset(
        {
            TaskGraphState.RUNNING,
            TaskGraphState.FAILURE_DRAINING,
            TaskGraphState.CANCEL_REQUESTED,
            TaskGraphState.SUCCEEDED,
            TaskGraphState.FAILED_FINAL,
            TaskGraphState.CANCELLED,
        }
    ),
    TaskGraphState.WAITING: frozenset(
        {
            TaskGraphState.RUNNING,
            TaskGraphState.PAUSED,
            TaskGraphState.FAILURE_DRAINING,
            TaskGraphState.CANCEL_REQUESTED,
            TaskGraphState.SUCCEEDED,
            TaskGraphState.FAILED_FINAL,
            TaskGraphState.CANCELLED,
        }
    ),
    TaskGraphState.FAILURE_DRAINING: frozenset(
        {TaskGraphState.FAILED_FINAL, TaskGraphState.CANCEL_REQUESTED, TaskGraphState.CANCELLED}
    ),
    TaskGraphState.CANCEL_REQUESTED: frozenset({TaskGraphState.CANCELLED}),
    TaskGraphState.SUCCEEDED: frozenset(),
    TaskGraphState.FAILED_FINAL: frozenset(),
    TaskGraphState.CANCELLED: frozenset(),
}


def assert_task_transition(source: TaskState, target: TaskState) -> None:
    if source == target:
        return
    if target not in _TASK_TRANSITIONS[source]:
        raise TaskGraphStateError(f"TASK_STATE_TRANSITION_INVALID:{source.value}->{target.value}")


def assert_graph_transition(source: TaskGraphState, target: TaskGraphState) -> None:
    if source == target:
        return
    if target not in _GRAPH_TRANSITIONS[source]:
        raise TaskGraphStateError(f"TASK_GRAPH_TRANSITION_INVALID:{source.value}->{target.value}")
