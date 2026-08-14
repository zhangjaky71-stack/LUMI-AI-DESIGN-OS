class MemoryEngineError(RuntimeError):
    pass


class MemoryScopeError(MemoryEngineError):
    pass


class MemorySensitivityError(MemoryEngineError):
    pass


class MemoryConflictError(MemoryEngineError):
    pass


class MemoryRetentionError(MemoryEngineError):
    pass
