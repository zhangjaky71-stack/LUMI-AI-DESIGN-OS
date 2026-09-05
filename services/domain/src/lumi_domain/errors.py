from __future__ import annotations


class DomainError(ValueError):
    """Base class for business-rule violations."""


class InvariantViolation(DomainError):
    """Raised when an aggregate invariant would be broken."""


class InvalidTransition(DomainError):
    """Raised when a state-machine transition is not allowed."""
