from __future__ import annotations


class TaskGraphError(RuntimeError):
    code = "TASK_GRAPH_ERROR"


class TaskGraphConflictError(TaskGraphError):
    code = "TASK_GRAPH_CONFLICT"


class TaskGraphLeaseError(TaskGraphError):
    code = "TASK_GRAPH_LEASE_ERROR"


class TaskGraphStateError(TaskGraphError):
    code = "TASK_GRAPH_STATE_ERROR"


class TaskGraphBudgetError(TaskGraphError):
    code = "TASK_GRAPH_BUDGET_ERROR"


class TaskGraphDefinitionError(TaskGraphError):
    code = "TASK_GRAPH_DEFINITION_ERROR"
