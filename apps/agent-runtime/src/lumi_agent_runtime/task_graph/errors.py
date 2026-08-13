class TaskGraphError(RuntimeError):
    pass


class TaskGraphStateError(TaskGraphError):
    pass


class TaskGraphClaimError(TaskGraphError):
    pass


class TaskGraphLeaseError(TaskGraphError):
    pass


class TaskGraphConflictError(TaskGraphError):
    pass


class TaskGraphBudgetError(TaskGraphError):
    pass


class TaskGraphExpansionError(TaskGraphError):
    pass
