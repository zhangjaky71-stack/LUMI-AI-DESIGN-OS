from __future__ import annotations

from .errors import TaskGraphStateError
from .states import TaskState

_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PENDING: frozenset({TaskState.READY, TaskState.CANCELLED, TaskState.SKIPPED}),
    TaskState.READY: frozenset({TaskState.RUNNING, TaskState.CANCELLED, TaskState.SKIPPED}),
    TaskState.RUNNING: frozenset({
        TaskState.SUCCEEDED,
        TaskState.FAILED_RETRYABLE,
        TaskState.FAILED_FINAL,
        TaskState.WAITING_APPROVAL,
        TaskState.WAITING_INPUT,
        TaskState.WAITING_EXTERNAL,
        TaskState.CANCELLED,
    }),
    TaskState.WAITING_APPROVAL: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.WAITING_INPUT: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.WAITING_EXTERNAL: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.FAILED_RETRYABLE: frozenset({TaskState.READY, TaskState.FAILED_FINAL, TaskState.CANCELLED}),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED_FINAL: frozenset(),
    TaskState.CANCELLED: frozenset(),
    TaskState.SKIPPED: frozenset(),
}


def assert_transition(current: TaskState, target: TaskState) -> None:
    if target not in _ALLOWED[current]:
        raise TaskGraphStateError(f"TASK_STATE_TRANSITION_FORBIDDEN:{current}->{target}")


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in _ALLOWED[current]
