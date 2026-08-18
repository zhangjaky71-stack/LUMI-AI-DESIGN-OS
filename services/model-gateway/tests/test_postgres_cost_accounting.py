from __future__ import annotations

import json
import unittest
from decimal import Decimal
from uuid import UUID, uuid4

from lumi_model_gateway import (
    BudgetExceededError,
    Capability,
    CostConfidence,
    CostEstimate,
    LedgerBudgetGuard,
    ModelRequest,
    PostgresCostAccounting,
)
from lumi_model_gateway.postgres_cost_accounting import CostAccountingDatabaseError


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.value: object = uuid4()
        self.error: Exception | None = None

    async def fetchval(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        return self.value


def request() -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        operation_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        agent_run_id=uuid4(),
        generation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs={"prompt": "global spend guard"},
    )


class PostgresCostAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_reserve_uses_database_atomic_function(self) -> None:
        connection = FakeConnection()
        accounting = PostgresCostAccounting(connection)
        req = request()
        ticket = await accounting.reserve_provider_cost(
            organization_id=req.organization_id,
            operation_id=req.operation_id,
            project_id=req.project_id,
            task_id=req.task_id,
            agent_run_id=req.agent_run_id,
            generation_id=req.generation_id,
            provider="alpha",
            model="reasoner-v1",
            estimated_amount_usd=Decimal("0.25"),
            confidence="estimated",
            pricing_snapshot_id="price-v1",
            reservation_key="model:alpha:reasoner-v1",
        )
        self.assertTrue(UUID(ticket))
        query, args = connection.calls[0]
        self.assertIn("provider_cost_reserve", query)
        self.assertEqual(args[0], req.organization_id)
        self.assertEqual(args[8], Decimal("0.25"))
        self.assertEqual(args[11], "model:alpha:reasoner-v1")
        self.assertIsInstance(args[12], UUID)

    async def test_daily_cap_rejection_normalizes_to_budget_error(self) -> None:
        connection = FakeConnection()
        connection.error = RuntimeError("COST_DAILY_CAP_EXCEEDED")
        guard = LedgerBudgetGuard(PostgresCostAccounting(connection))
        with self.assertRaises(BudgetExceededError):
            await guard.reserve(
                request=request(),
                provider="alpha",
                model="reasoner-v1",
                estimate=CostEstimate(
                    amount_usd=Decimal("1.00"),
                    confidence=CostConfidence.ESTIMATED,
                ),
            )

    async def test_accounting_outage_fails_closed_before_provider(self) -> None:
        connection = FakeConnection()
        connection.error = RuntimeError("database unavailable")
        accounting = PostgresCostAccounting(connection)
        with self.assertRaises(CostAccountingDatabaseError) as caught:
            await accounting.reserve_provider_cost(
                organization_id=uuid4(),
                operation_id=uuid4(),
                project_id=None,
                task_id=None,
                agent_run_id=None,
                generation_id=None,
                provider="alpha",
                model="reasoner-v1",
                estimated_amount_usd=Decimal("0.10"),
                confidence="estimated",
                pricing_snapshot_id=None,
                reservation_key="model:alpha:reasoner-v1",
            )
        self.assertEqual(caught.exception.code, "COST_GUARD_UNAVAILABLE")

    async def test_commit_serializes_decimal_usage_without_float(self) -> None:
        connection = FakeConnection()
        accounting = PostgresCostAccounting(connection)
        ticket = str(uuid4())
        await accounting.commit_provider_cost(
            reservation_ticket=ticket,
            actual_amount_usd=Decimal("0.27"),
            confidence="exact",
            pricing_snapshot_id="price-v2",
            provider_request_id="provider-123",
            usage={
                "images": (Decimal("2"), "units"),
                "input_tokens": (Decimal("100"), "tokens"),
            },
        )
        query, args = connection.calls[0]
        self.assertIn("provider_cost_commit", query)
        payload = json.loads(str(args[5]))
        self.assertEqual(payload["images"], {"quantity": "2", "unit": "units"})
        self.assertEqual(
            payload["input_tokens"], {"quantity": "100", "unit": "tokens"}
        )

    async def test_release_calls_atomic_release_function(self) -> None:
        connection = FakeConnection()
        accounting = PostgresCostAccounting(connection)
        ticket = str(uuid4())
        await accounting.release_provider_cost(
            reservation_ticket=ticket,
            reason="provider_not_accepted",
        )
        query, args = connection.calls[0]
        self.assertIn("provider_cost_release", query)
        self.assertEqual(args[0], UUID(ticket))
        self.assertEqual(args[1], "provider_not_accepted")

    async def test_non_positive_estimate_rejected_without_database_call(self) -> None:
        connection = FakeConnection()
        accounting = PostgresCostAccounting(connection)
        with self.assertRaises(CostAccountingDatabaseError):
            await accounting.reserve_provider_cost(
                organization_id=uuid4(),
                operation_id=uuid4(),
                project_id=None,
                task_id=None,
                agent_run_id=None,
                generation_id=None,
                provider="alpha",
                model="reasoner-v1",
                estimated_amount_usd=Decimal("0"),
                confidence="estimated",
                pricing_snapshot_id=None,
                reservation_key="model:alpha:reasoner-v1",
            )
        self.assertEqual(connection.calls, [])


if __name__ == "__main__":
    unittest.main()
