from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import AsyncIterator

import asyncpg

from .contracts import (
    ActualCost,
    BudgetExceeded,
    BudgetReservationRequest,
    LedgerWriteResult,
    ReservationHandle,
)
from .gateway import PostgresCostGateway


class PlatformProviderCostGuardUnavailable(BudgetExceeded):
    """The platform hard stop is missing, disabled, or not fail-closed."""


class PlatformGuardedCostGateway(PostgresCostGateway):
    """NODE-27 gateway with a platform-wide USD/UTC-day reservation boundary.

    The canonical financial facts remain ``cost_ledger`` and ``cost_reservations``.
    A PostgreSQL advisory transaction lock serializes provider-cost reservations
    across *all* organizations. The lock is intentionally held while the base
    NODE-27 gateway performs its own durable reserve/commit/release transaction,
    so a second process cannot observe a gap between global preflight and the
    canonical reservation/actual-cost write.
    """

    _LOCK_KEY = "cost-budget:platform:provider-usd:utc-day"

    async def reserve(self, request: BudgetReservationRequest) -> ReservationHandle:
        if request.currency != "USD":
            raise PlatformProviderCostGuardUnavailable(
                "platform provider hard stop currently requires USD accounting"
            )
        async with self._platform_lock() as connection:
            await self._require_capacity(connection, request.estimated_amount)
            return await super().reserve(request)

    async def commit(
        self,
        handle: ReservationHandle,
        actual: ActualCost,
    ) -> LedgerWriteResult:
        # Actual provider cost is sunk once work was accepted. Serialize the write
        # with new reservations but never reject the financial fact because the
        # actual exceeded its estimate; the next reservation will fail closed.
        async with self._platform_lock():
            return await super().commit(handle, actual)

    async def release(self, handle: ReservationHandle, *, reason: str) -> None:
        async with self._platform_lock():
            await super().release(handle, reason=reason)

    async def remaining_platform_daily_budget(self) -> Decimal:
        async with self._platform_lock() as connection:
            cap, spent, active = await self._snapshot(connection)
            return max(Decimal("0"), cap - spent - active)

    @asynccontextmanager
    async def _platform_lock(self) -> AsyncIterator[asyncpg.Connection]:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                    self._LOCK_KEY,
                )
                yield connection
        finally:
            await connection.close()

    async def _require_capacity(
        self,
        connection: asyncpg.Connection,
        projected_amount: Decimal,
    ) -> None:
        cap, spent, active = await self._snapshot(connection)
        if spent + active + projected_amount > cap:
            raise BudgetExceeded(
                "platform daily provider budget exceeded: "
                f"spent={spent} active={active} "
                f"requested={projected_amount} max={cap}"
            )

    async def _snapshot(
        self,
        connection: asyncpg.Connection,
    ) -> tuple[Decimal, Decimal, Decimal]:
        policy = await connection.fetchrow(
            """
            SELECT daily_cap_usd, enabled, fail_closed
            FROM platform_provider_cost_guard
            WHERE policy_key='platform'
            """
        )
        if policy is None or not policy["enabled"] or not policy["fail_closed"]:
            raise PlatformProviderCostGuardUnavailable(
                "platform provider cost guard must exist, be enabled, and fail closed"
            )

        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        spent = await connection.fetchval(
            """
            SELECT COALESCE(sum(amount),0)
            FROM cost_ledger
            WHERE currency='USD'
              AND cost_basis='provider_cost'
              AND entry_type IN ('actual_cost','adjustment','reversal')
              AND occurred_at >= $1 AND occurred_at < $2
            """,
            start,
            end,
        )
        active = await connection.fetchval(
            """
            SELECT COALESCE(sum(estimated_amount),0)
            FROM cost_reservations
            WHERE currency='USD'
              AND status='active'
              AND expires_at > now()
            """
        )
        return (
            Decimal(policy["daily_cap_usd"]),
            Decimal(spent),
            Decimal(active),
        )
