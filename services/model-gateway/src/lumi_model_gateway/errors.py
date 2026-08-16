from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    PROVIDER_5XX = "provider_5xx"
    CAPABILITY_TEMP_UNAVAILABLE = "capability_temp_unavailable"
    AUTH_ERROR = "auth_error"
    INVALID_REQUEST = "invalid_request"
    USER_CONTENT_POLICY_BLOCK = "user_content_policy_block"
    BUDGET_EXCEEDED = "budget_exceeded"
    HARD_CONSTRAINT_INVALID = "hard_constraint_invalid"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNKNOWN = "unknown"


class ProviderAcceptance(StrEnum):
    NOT_ACCEPTED = "not_accepted"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"


FALLBACK_ALLOWED = frozenset(
    {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.PROVIDER_5XX,
        ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
    }
)


@dataclass(slots=True)
class ProviderCallError(RuntimeError):
    category: ErrorCategory
    message: str
    provider: str | None = None
    status_code: int | None = None
    retry_after_seconds: float | None = None
    provider_request_id: str | None = None
    retryable: bool = False
    acceptance: ProviderAcceptance = ProviderAcceptance.UNKNOWN

    def __str__(self) -> str:
        return self.message

    @property
    def fallback_allowed(self) -> bool:
        return self.category in FALLBACK_ALLOWED

    @property
    def ambiguous_paid_effect(self) -> bool:
        return (
            self.acceptance is ProviderAcceptance.UNKNOWN
            and self.category is ErrorCategory.TIMEOUT
        )


class NoRouteAvailable(RuntimeError):
    code = "MODEL_GATEWAY_NO_ROUTE"


class PaidSideEffectGuardRequired(RuntimeError):
    code = "MODEL_GATEWAY_PAID_SIDE_EFFECT_GUARD_REQUIRED"


class PaidSideEffectSemanticConflict(RuntimeError):
    code = "MODEL_GATEWAY_PAID_SIDE_EFFECT_SEMANTIC_CONFLICT"


class SecretUnavailable(RuntimeError):
    code = "MODEL_GATEWAY_SECRET_UNAVAILABLE"


class UnsupportedProviderOperation(RuntimeError):
    code = "MODEL_GATEWAY_PROVIDER_OPERATION_UNSUPPORTED"
