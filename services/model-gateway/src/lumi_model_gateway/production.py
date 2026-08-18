from __future__ import annotations

from .budget import RequestBudgetGuard
from .cost_accounting import LedgerBudgetGuard
from .ports import BudgetGuard
from .postgres_cost_accounting import CostAccountingConnection, PostgresCostAccounting


class DurableCostGuardRequiredError(RuntimeError):
    """Hosted execution must never fall back to request-local cost enforcement."""


_HOSTED_ENVIRONMENTS = frozenset({"staging", "production"})


def build_environment_budget_guard(
    *,
    environment: str,
    accounting_connection: CostAccountingConnection | None,
) -> BudgetGuard:
    """Build the budget guard without allowing a hosted fail-open composition.

    Local/test/development retain the request-local guard for hermetic tests and
    developer workflows. Staging and production require the PostgreSQL-backed
    NODE-27 adapter so every paid provider invocation participates in the shared
    platform USD/day reservation lock before the provider is called.
    """

    normalized = environment.strip().lower()
    if normalized in _HOSTED_ENVIRONMENTS:
        if accounting_connection is None:
            raise DurableCostGuardRequiredError(
                "COST_GUARD_DURABLE_ACCOUNTING_REQUIRED"
            )
        return LedgerBudgetGuard(PostgresCostAccounting(accounting_connection))
    return RequestBudgetGuard()
