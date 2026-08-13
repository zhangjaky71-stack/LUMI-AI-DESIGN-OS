from __future__ import annotations


class ApplicationError(RuntimeError):
    code = "APPLICATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResourceNotFound(ApplicationError):
    code = "RESOURCE_NOT_FOUND"


class Conflict(ApplicationError):
    code = "CONFLICT"


class AccessDenied(ApplicationError):
    code = "ACCESS_DENIED"


class PreconditionFailed(ApplicationError):
    code = "PRECONDITION_FAILED"


class IdempotencyConflict(ApplicationError):
    code = "IDEMPOTENCY_CONFLICT"


class ApplicationInvariantViolation(ApplicationError):
    code = "APPLICATION_INVARIANT_VIOLATION"
