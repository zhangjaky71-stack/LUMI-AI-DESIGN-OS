from __future__ import annotations

from enum import StrEnum


class ErrorCategory(StrEnum):
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    PROVIDER_5XX = "PROVIDER_5XX"
    CAPABILITY_TEMP_UNAVAILABLE = "CAPABILITY_TEMP_UNAVAILABLE"
    AUTH_ERROR = "AUTH_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    USER_CONTENT_POLICY_BLOCK = "USER_CONTENT_POLICY_BLOCK"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    HARD_CONSTRAINT_INVALID = "HARD_CONSTRAINT_INVALID"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class DeliveryState(StrEnum):
    NOT_ACCEPTED = "not_accepted"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"


_FALLBACKABLE = frozenset(
    {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.PROVIDER_5XX,
        ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
        ErrorCategory.PROVIDER_UNAVAILABLE,
    }
)
_RETRYABLE = frozenset(
    {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.PROVIDER_5XX,
        ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
        ErrorCategory.PROVIDER_UNAVAILABLE,
    }
)


class ModelGatewayError(RuntimeError):
    code = "MODEL_GATEWAY_ERROR"


class NoRouteError(ModelGatewayError):
    code = "MODEL_NO_ROUTE"


class BudgetExceededError(ModelGatewayError):
    code = "MODEL_BUDGET_EXCEEDED"


class PaidInvocationGuardRequiredError(ModelGatewayError):
    code = "MODEL_PAID_INVOCATION_GUARD_REQUIRED"


class DurableBudgetGuardRequiredError(ModelGatewayError):
    code = "MODEL_DURABLE_BUDGET_GUARD_REQUIRED"


class AmbiguousProviderOutcomeError(ModelGatewayError):
    code = "MODEL_PROVIDER_OUTCOME_AMBIGUOUS"


class ProviderInvocationError(ModelGatewayError):
    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        provider: str,
        model: str,
        delivery_state: DeliveryState = DeliveryState.UNKNOWN,
        retry_after_seconds: float | None = None,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message[:2000])
        self.category = category
        self.provider = provider
        self.model = model
        self.delivery_state = delivery_state
        self.retry_after_seconds = retry_after_seconds
        self.provider_code = provider_code

    @property
    def retryable(self) -> bool:
        return self.category in _RETRYABLE

    @property
    def fallbackable(self) -> bool:
        return (
            self.category in _FALLBACKABLE
            and self.delivery_state == DeliveryState.NOT_ACCEPTED
        )

    @property
    def ambiguous(self) -> bool:
        return self.delivery_state in {
            DeliveryState.ACCEPTED,
            DeliveryState.UNKNOWN,
        }


class ProviderValidationError(ProviderInvocationError):
    pass
