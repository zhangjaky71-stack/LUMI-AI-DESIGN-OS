from __future__ import annotations

import unittest

from lumi_model_gateway import (
    DurableCostGuardRequiredError,
    LedgerBudgetGuard,
    RequestBudgetGuard,
    build_environment_budget_guard,
)


class FakeConnection:
    async def fetchval(self, query: str, *args: object) -> object:
        del query, args
        return None


class ProductionCostGuardTests(unittest.TestCase):
    def test_production_refuses_request_local_fallback(self) -> None:
        with self.assertRaises(DurableCostGuardRequiredError):
            build_environment_budget_guard(
                environment="production",
                accounting_connection=None,
            )

    def test_staging_refuses_request_local_fallback(self) -> None:
        with self.assertRaises(DurableCostGuardRequiredError):
            build_environment_budget_guard(
                environment="staging",
                accounting_connection=None,
            )

    def test_hosted_environment_builds_ledger_guard(self) -> None:
        guard = build_environment_budget_guard(
            environment="production",
            accounting_connection=FakeConnection(),
        )
        self.assertIsInstance(guard, LedgerBudgetGuard)

    def test_local_environment_keeps_hermetic_request_guard(self) -> None:
        guard = build_environment_budget_guard(
            environment="development",
            accounting_connection=None,
        )
        self.assertIsInstance(guard, RequestBudgetGuard)


if __name__ == "__main__":
    unittest.main()
