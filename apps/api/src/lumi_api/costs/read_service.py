from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


class PostgresCostReadService:
    """Tenant-scoped read projection for cost/usage API endpoints."""

    def __init__(self, dsn: str) -> None:
        self.dsn = _asyncpg_dsn(dsn)

    async def summary(
        self,
        *,
        organization_id: UUID,
        from_time: datetime,
        to_time: datetime,
        project_id: UUID | None = None,
        currency: str = "USD",
    ) -> dict[str, Any]:
        _validate_range(from_time, to_time)
        asyncpg = _asyncpg()
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                args: list[Any] = [organization_id, from_time, to_time, currency]
                project_clause = ""
                if project_id is not None:
                    args.append(project_id)
                    project_clause = f" AND project_id=${len(args)}"
                row = await connection.fetchrow(
                    f"""
                    SELECT
                      COALESCE(sum(amount) FILTER (WHERE entry_type='actual_cost'),0)
                        AS actual_cost,
                      COALESCE(sum(amount) FILTER (WHERE entry_type='adjustment'),0)
                        AS adjustments,
                      COALESCE(sum(amount) FILTER (WHERE entry_type='reversal'),0)
                        AS reversals,
                      count(*) FILTER (
                        WHERE entry_type='actual_cost' AND confidence <> 'exact'
                      ) AS non_exact_entries
                    FROM cost_ledger
                    WHERE organization_id=$1
                      AND occurred_at >= $2 AND occurred_at < $3
                      AND currency=$4 AND cost_basis='provider_cost'
                      AND entry_type IN ('actual_cost','adjustment','reversal')
                      {project_clause}
                    """,
                    *args,
                )
                reservation_args: list[Any] = [organization_id, currency]
                reservation_project_clause = ""
                if project_id is not None:
                    reservation_args.append(project_id)
                    reservation_project_clause = (
                        f" AND project_id=${len(reservation_args)}"
                    )
                active = await connection.fetchval(
                    f"""
                    SELECT COALESCE(sum(estimated_amount),0)
                    FROM cost_reservations
                    WHERE organization_id=$1 AND currency=$2
                      AND status='active' AND expires_at > now()
                      {reservation_project_clause}
                    """,
                    *reservation_args,
                )
        finally:
            await connection.close()
        actual = Decimal(row["actual_cost"])
        adjustments = Decimal(row["adjustments"])
        reversals = Decimal(row["reversals"])
        return {
            "organization_id": organization_id,
            "project_id": project_id,
            "currency": currency,
            "actual_cost": actual,
            "adjustments": adjustments,
            "reversals": reversals,
            "net_provider_cost": actual + adjustments + reversals,
            "active_reservations": Decimal(active),
            "non_exact_entries": int(row["non_exact_entries"]),
            "from_time": from_time,
            "to_time": to_time,
        }

    async def usage(
        self,
        *,
        organization_id: UUID,
        from_time: datetime,
        to_time: datetime,
        project_id: UUID | None = None,
    ) -> tuple[dict[str, Any], ...]:
        _validate_range(from_time, to_time)
        asyncpg = _asyncpg()
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                args: list[Any] = [organization_id, from_time, to_time]
                project_clause = ""
                if project_id is not None:
                    args.append(project_id)
                    project_clause = f" AND project_id=${len(args)}"
                rows = await connection.fetch(
                    f"""
                    SELECT metric, unit, sum(quantity) AS quantity
                    FROM usage_ledger
                    WHERE organization_id=$1
                      AND occurred_at >= $2 AND occurred_at < $3
                      {project_clause}
                    GROUP BY metric, unit ORDER BY metric, unit
                    """,
                    *args,
                )
        finally:
            await connection.close()
        return tuple(
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "metric": row["metric"],
                "quantity": Decimal(row["quantity"]),
                "unit": row["unit"],
                "from_time": from_time,
                "to_time": to_time,
            }
            for row in rows
        )


def _asyncpg() -> Any:
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError("COST_ASYNCPG_DEPENDENCY_NOT_INSTALLED") from exc
    return asyncpg


def _asyncpg_dsn(dsn: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if dsn.startswith(prefix):
            return "postgresql://" + dsn[len(prefix) :]
    return dsn


async def _set_tenant(connection: Any, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id',$1,true)",
        str(organization_id),
    )


def _validate_range(from_time: datetime, to_time: datetime) -> None:
    if from_time.tzinfo is None or to_time.tzinfo is None or from_time >= to_time:
        raise ValueError("COST_TIME_RANGE_INVALID")
