from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from .errors import BudgetExceededError
from .models import CostConfidence, CostEstimate, ModelRequest, Usage


class CostAccountingPort(Protocol):
    """DB-neutral durable accounting boundary implemented by NODE-27 infrastructure."""

    async def reserve_provider_cost(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        project_id: UUID | None,
        task_id: UUID | None,
        agent_run_id: UUID | None,
        generation_id: UUID | None,
        provider: str,
        model: str,
        estimated_amount_usd: Decimal,
        confidence: str,
        pricing_snapshot_id: str | None,
        reservation_key: str,
    ) -> str: ...

    async def commit_provider_cost(
        self,
        *,
        reservation_ticket: str,
        actual_amount_usd: Decimal,
        confidence: str,
        pricing_snapshot_id: str | None,
        provider_request_id: str | None,
        usage: dict[str, tuple[Decimal, str]],
    ) -> None: ...

    async def release_provider_cost(
        self,
        *,
        reservation_ticket: str,
        reason: str,
    ) -> None: ...


@dataclass(slots=True)
class _LedgerBudgetReservation:
    accounting: CostAccountingPort
    ticket: str
    request_limit: Decimal | None
    estimate: CostEstimate
    committed: bool = False
    released: bool = False

    async def commit(
        self,
        actual: CostEstimate,
        *,
        usage: Usage | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        if self.released:
            raise RuntimeError("MODEL_BUDGET_RESERVATION_RELEASED")
        amount = actual.amount_usd
        if amount is None:
            amount = self.estimate.amount_usd
            if amount is None:
                raise BudgetExceededError(
                    "accepted provider operation has neither actual nor estimated cost"
                )
        confidence = actual.confidence
        if actual.amount_usd is None:
            confidence = (
                self.estimate.confidence
                if self.estimate.confidence != CostConfidence.EXACT
                else CostConfidence.ESTIMATED
            )
        await self.accounting.commit_provider_cost(
            reservation_ticket=self.ticket,
            actual_amount_usd=amount,
            confidence=confidence.value,
            pricing_snapshot_id=actual.price_snapshot_id or self.estimate.price_snapshot_id,
            provider_request_id=provider_request_id,
            usage=_usage_map(usage),
        )
        self.committed = True

    async def release(self, *, reason: str = "not_accepted") -> None:
        if self.committed or self.released:
            return
        await self.accounting.release_provider_cost(
            reservation_ticket=self.ticket,
            reason=reason,
        )
        self.released = True


class LedgerBudgetGuard:
    """NODE-27 durable BudgetGuard for ModelGateway."""

    def __init__(self, accounting: CostAccountingPort) -> None:
        self.accounting = accounting

    async def reserve(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        estimate: CostEstimate,
    ) -> _LedgerBudgetReservation:
        amount = estimate.amount_usd
        if request.budget_limit_usd is not None:
            if amount is None:
                raise BudgetExceededError(
                    "request has a hard budget but provider cost cannot be estimated"
                )
            if amount > request.budget_limit_usd:
                raise BudgetExceededError(
                    f"estimated cost {amount} exceeds request budget {request.budget_limit_usd}"
                )
        if amount is None:
            raise BudgetExceededError(
                "durable budget reservation requires an estimated provider cost"
            )
        try:
            ticket = await self.accounting.reserve_provider_cost(
                organization_id=request.organization_id,
                operation_id=request.operation_id,
                project_id=request.project_id,
                task_id=request.task_id,
                agent_run_id=request.agent_run_id,
                generation_id=request.generation_id,
                provider=provider,
                model=model,
                estimated_amount_usd=amount,
                confidence=estimate.confidence.value,
                pricing_snapshot_id=estimate.price_snapshot_id,
                reservation_key=f"model:{provider}:{model}",
            )
        except Exception as exc:
            if getattr(exc, "code", None) in {
                "COST_BUDGET_EXCEEDED",
                "COST_QUOTA_EXCEEDED",
            }:
                raise BudgetExceededError(str(exc)) from exc
            raise
        return _LedgerBudgetReservation(
            accounting=self.accounting,
            ticket=ticket,
            request_limit=request.budget_limit_usd,
            estimate=estimate,
        )


def _usage_map(usage: Usage | None) -> dict[str, tuple[Decimal, str]]:
    if usage is None:
        return {}
    mapped: dict[str, tuple[Decimal, str]] = {}
    token_fields = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "image_input_tokens": usage.image_input_tokens,
        "image_output_tokens": usage.image_output_tokens,
    }
    for metric, value in token_fields.items():
        if value is not None:
            mapped[metric] = (Decimal(value), "tokens")
    if usage.seconds is not None:
        mapped["seconds"] = (usage.seconds, "seconds")
    for metric, value in sorted(usage.units.items()):
        mapped[metric] = (value, "units")
    return mapped
