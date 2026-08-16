from __future__ import annotations

import os

from lumi_model_gateway import LedgerBudgetGuard

from .model_gateway_adapter import PostgresModelCostAccounting


class DurableModelBudgetConfigurationError(RuntimeError):
    code = "MODEL_DURABLE_BUDGET_CONFIGURATION_REQUIRED"


def build_durable_model_budget_guard(
    database_url: str | None = None,
) -> LedgerBudgetGuard:
    """Build the only production-safe Model Gateway budget guard.

    Production/staging composition must call this factory instead of constructing a
    RequestBudgetGuard. Missing database configuration fails before any provider can
    be invoked.
    """

    dsn = (database_url or os.getenv("LUMI_DATABASE_URL") or "").strip()
    if not dsn:
        raise DurableModelBudgetConfigurationError(
            "LUMI_DATABASE_URL is required for durable Model Gateway cost accounting"
        )
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise DurableModelBudgetConfigurationError(
            "LUMI_DATABASE_URL must be a PostgreSQL DSN"
        )
    return LedgerBudgetGuard(PostgresModelCostAccounting(dsn))
