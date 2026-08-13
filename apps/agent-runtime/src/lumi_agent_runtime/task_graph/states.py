from __future__ import annotations

from enum import StrEnum


class TaskState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class TaskGraphState(StrEnum):
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


TERMINAL_TASK_STATES = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.FAILED_FINAL,
        TaskState.CANCELLED,
        TaskState.SKIPPED,
    }
)
WAITING_TASK_STATES = frozenset(
    {
        TaskState.WAITING_APPROVAL,
        TaskState.WAITING_INPUT,
        TaskState.WAITING_EXTERNAL,
    }
)
