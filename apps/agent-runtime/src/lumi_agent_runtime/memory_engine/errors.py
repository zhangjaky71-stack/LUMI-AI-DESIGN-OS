from __future__ import annotations


class MemoryEngineError(RuntimeError):
    code = "MEMORY_ENGINE_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)


class MemoryPermissionError(MemoryEngineError):
    code = "MEMORY_PERMISSION_DENIED"


class MemoryConflictError(MemoryEngineError):
    code = "MEMORY_REVISION_CONFLICT"


class MemoryNotFoundError(MemoryEngineError):
    code = "MEMORY_NOT_FOUND"


class MemoryValidationError(MemoryEngineError):
    code = "MEMORY_VALIDATION_FAILED"
