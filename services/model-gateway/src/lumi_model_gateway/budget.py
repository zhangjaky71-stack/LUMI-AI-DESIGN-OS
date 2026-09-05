from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .errors import BudgetExceededError
from .models import CostEstimate, ModelRequest, Usage


@dataclass(slots=True)
class _RequestBudgetReservation:
    request_limit: Decimal | None
    reserved: Decimal | None
    committed: bool = False
    released: bool = False

    async def commit(
        self,
        actual: CostEstimate,
        *,
        usage: Usage | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        del actual, usage, provider_request_id
        if self.released:
            raise RuntimeError("MODEL_BUDGET_RESERVATION_RELEASED")
        # Budget enforcement is pre-invocation. Once the provider accepted a paid
        # operation, accounting must not erase the sunk cost because actual spend
        # exceeded the estimate. Durable NODE-27 guards block subsequent spend.
        self.committed = True

    async def release(self, *, reason: str = "not_accepted") -> None:
        del reason
        if not self.committed:
            self.released = True


class RequestBudgetGuard:
    """Request-local fallback; NODE-27 LedgerBudgetGuard is the durable production path."""

    async def reserve(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        estimate: CostEstimate,
    ) -> _RequestBudgetReservation:
        del provider, model
        limit = request.budget_limit_usd
        if limit is not None:
            if estimate.amount_usd is None:
                raise BudgetExceededError(
                    "request has a hard budget but provider cost cannot be estimated"
                )
            if estimate.amount_usd > limit:
                raise BudgetExceededError(
                    f"estimated cost {estimate.amount_usd} exceeds request budget {limit}"
                )
        return _RequestBudgetReservation(
            request_limit=limit,
            reserved=estimate.amount_usd,
        )
