class ContextEngineError(RuntimeError):
    """Base NODE-34 Context Engine error."""


class ContextIdentityError(ContextEngineError):
    pass


class ContextBudgetError(ContextEngineError):
    pass


class ContextSourceError(ContextEngineError):
    pass


class ContextPermissionError(ContextEngineError):
    pass


class ContextIntegrityError(ContextEngineError):
    pass
