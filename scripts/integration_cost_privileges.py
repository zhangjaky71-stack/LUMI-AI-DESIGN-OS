from __future__ import annotations

import asyncio
import os

import asyncpg


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


async def _must_be_denied(
    connection: asyncpg.Connection,
    statement: str,
) -> None:
    try:
        await connection.execute(statement)
    except asyncpg.InsufficientPrivilegeError:
        return
    raise AssertionError(f"runtime mutation must be denied: {statement}")


async def main_async() -> None:
    connection = await asyncpg.connect(_dsn("DATABASE_URL"))
    try:
        # WHERE false still forces PostgreSQL to evaluate table-level privileges without
        # changing seeded data. These checks protect against 0002 default privileges on
        # tables created by later lumi_migration revisions.
        for statement in (
            "UPDATE cost_ledger SET amount=amount WHERE false",
            "DELETE FROM cost_ledger WHERE false",
            "UPDATE usage_ledger SET quantity=quantity WHERE false",
            "DELETE FROM usage_ledger WHERE false",
            "DELETE FROM cost_reservations WHERE false",
            "INSERT INTO cost_budget_limits (id, organization_id, scope_type, period_key, amount_limit, currency) SELECT gen_random_uuid(), id, 'organization', 'lifetime', 1, 'USD' FROM organizations WHERE false",
            "UPDATE cost_budget_limits SET amount_limit=amount_limit WHERE false",
            "DELETE FROM cost_budget_limits WHERE false",
            "INSERT INTO quota_limits (id, organization_id, scope_type, metric, period_key, quantity_limit, unit) SELECT gen_random_uuid(), id, 'organization', 'test', 'lifetime', 1, 'units' FROM organizations WHERE false",
            "UPDATE quota_limits SET quantity_limit=quantity_limit WHERE false",
            "DELETE FROM quota_limits WHERE false",
            "DELETE FROM quota_leases WHERE false",
        ):
            await _must_be_denied(connection, statement)
    finally:
        await connection.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-27 runtime financial privilege integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
