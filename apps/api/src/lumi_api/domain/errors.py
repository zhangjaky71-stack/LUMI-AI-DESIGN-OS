class DomainError(Exception):
    """Base class for domain-level rule violations."""


class InvariantViolation(DomainError):
    """Raised when a domain invariant would be broken."""


class InvalidTransition(DomainError):
    """Raised when a state machine transition is not allowed."""
