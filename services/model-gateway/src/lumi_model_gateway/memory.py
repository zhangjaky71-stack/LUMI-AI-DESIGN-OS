from __future__ import annotations

import asyncio
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from .errors import PaidSideEffectSemanticConflict
from .models import CostEstimate, HealthSnapshot, ModelRequest, NormalizedResult, RouteCandidate
from .ports import BudgetReservation, CostTelemetry, PaidEffect, ReconcileEffect


class MemoryHealthPort:
    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str], HealthSnapshot] = {}
        self.successes: dict[tuple[str, str], int] = defaultdict(int)
        self.failures: dict[tuple[str, str], int] = defaultdict(int)

    def set(self, provider: str, model: str, snapshot: HealthSnapshot) -> None:
        self._snapshots[(provider, model)] = snapshot

    def snapshot(self, provider: str, model: str) -> HealthSnapshot:
        return self._snapshots.get((provider, model), HealthSnapshot())

    def record_success(self, provider: str, model: str, latency_ms: int | None) -> None:
        del latency_ms
        self.successes[(provider, model)] += 1

    def record_failure(self, provider: str, model: str, category: str) -> None:
        del category
        self.failures[(provider, model)] += 1


class MemoryBudgetPort:
    def __init__(self, remaining_usd: Decimal | None = None) -> None:
        self.remaining_usd = remaining_usd
        self.reserved: dict[str, Decimal] = {}

    async def reserve(
        self, request: ModelRequest, candidate: RouteCandidate
    ) -> BudgetReservation:
        amount = candidate.estimate.amount_usd
        effective_limit = request.budget_limit
        if amount is None:
            if not request.routing_hints.allow_unknown_cost:
                return BudgetReservation(False, reason="unknown_cost")
            return BudgetReservation(True, reservation_ref=f"unknown:{uuid4()}")
        if effective_limit is not None and amount > effective_limit:
            return BudgetReservation(
                False,
                remaining_usd=effective_limit,
                reason="operation_budget",
            )
        if self.remaining_usd is not None and amount > self.remaining_usd:
            return BudgetReservation(
                False,
                remaining_usd=self.remaining_usd,
                reason="remaining_budget",
            )
        ref = str(uuid4())
        self.reserved[ref] = amount
        if self.remaining_usd is not None:
            self.remaining_usd -= amount
        return BudgetReservation(
            True,
            reservation_ref=ref,
            remaining_usd=self.remaining_usd,
        )

    async def settle(
        self, reservation: BudgetReservation, *, actual: CostEstimate
    ) -> None:
        if not reservation.reservation_ref:
            return
        estimated = self.reserved.pop(reservation.reservation_ref, Decimal("0"))
        if self.remaining_usd is not None and actual.amount_usd is not None:
            self.remaining_usd += estimated - actual.amount_usd

    async def release(self, reservation: BudgetReservation) -> None:
        if not reservation.reservation_ref:
            return
        amount = self.reserved.pop(reservation.reservation_ref, Decimal("0"))
        if self.remaining_usd is not None:
            self.remaining_usd += amount


class MemoryCostTelemetryPort:
    def __init__(self) -> None:
        self.records: list[CostTelemetry] = []

    async def record(self, telemetry: CostTelemetry) -> None:
        self.records.append(telemetry)


class MemoryPaidSideEffectPort:
    """Deterministic CI reference only. Production must bind NODE-20 SideEffectGateway."""

    def __init__(self) -> None:
        self._results: dict[
            tuple[str, str, str, str], tuple[str, NormalizedResult]
        ] = {}
        self.executions = 0
        self._lock = asyncio.Lock()

    async def execute(
        self,
        *,
        request: ModelRequest,
        candidate: RouteCandidate,
        effect: PaidEffect,
        reconcile: ReconcileEffect | None = None,
    ) -> NormalizedResult:
        del reconcile
        key = (
            str(request.organization_id),
            str(request.operation_id),
            candidate.model.provider,
            candidate.model.model,
        )
        semantic_hash = request.semantic_hash()
        async with self._lock:
            existing = self._results.get(key)
            if existing is not None:
                existing_hash, result = existing
                if existing_hash != semantic_hash:
                    raise PaidSideEffectSemanticConflict(
                        PaidSideEffectSemanticConflict.code
                    )
                return result
            self.executions += 1
            result = await effect()
            self._results[key] = (semantic_hash, result)
            return result


class NullCostTelemetryPort:
    async def record(self, telemetry: CostTelemetry) -> None:
        del telemetry


class UnlimitedBudgetPort(MemoryBudgetPort):
    def __init__(self) -> None:
        super().__init__(remaining_usd=None)


async def no_sleep(seconds: float) -> None:
    del seconds
    await asyncio.sleep(0)
