class ContextEngineError(RuntimeError):
    pass


class ContextBudgetError(ContextEngineError):
    pass


class ContextSourceError(ContextEngineError):
    pass


class ContextScopeError(ContextEngineError):
    pass
