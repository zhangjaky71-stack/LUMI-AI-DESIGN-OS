from __future__ import annotations

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
    Usage,
)


class FakeAccounting:
    def __init__(self) -> None:
        self.reservations: list[dict[str, object]] = []
        self.commits: list[dict[str, object]] = []
        self.releases: list[dict[str, object]] = []
        self.reject_code: str | None = None

    async def reserve_provider_cost(self, **kwargs) -> str:
        if self.reject_code is not None:
            error = RuntimeError("durable budget denied")
            error.code = self.reject_code  # type: ignore[attr-defined]
            raise error
        self.reservations.append(dict(kwargs))
        return str(uuid4())

    async def commit_provider_cost(self, **kwargs) -> None:
        self.commits.append(dict(kwargs))

    async def release_provider_cost(self, **kwargs) -> None:
        self.releases.append(dict(kwargs))


def request(*, budget: Decimal | None = None) -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        operation_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        agent_run_id=uuid4(),
        generation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs={"prompt": "cost test"},
        budget_limit_usd=budget,
    )


class CostAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_reserve_freezes_full_allocation_context(self) -> None:
        accounting = FakeAccounting()
        guard = LedgerBudgetGuard(accounting)
        req = request(budget=Decimal("1.00"))
        reservation = await guard.reserve(
            request=req,
            provider="alpha",
            model="reasoner-v1",
            estimate=CostEstimate(
                amount_usd=Decimal("0.25"),
                confidence=CostConfidence.EXACT,
                price_snapshot_id="price-v7",
            ),
        )
        self.assertTrue(UUID(reservation.ticket))
        payload = accounting.reservations[0]
        self.assertEqual(payload["organization_id"], req.organization_id)
        self.assertEqual(payload["operation_id"], req.operation_id)
        self.assertEqual(payload["project_id"], req.project_id)
        self.assertEqual(payload["task_id"], req.task_id)
        self.assertEqual(payload["agent_run_id"], req.agent_run_id)
        self.assertEqual(payload["generation_id"], req.generation_id)
        self.assertEqual(payload["pricing_snapshot_id"], "price-v7")

    async def test_commit_records_actual_usage_and_provider_request(self) -> None:
        accounting = FakeAccounting()
        guard = LedgerBudgetGuard(accounting)
        reservation = await guard.reserve(
            request=request(budget=Decimal("1.00")),
            provider="alpha",
            model="reasoner-v1",
            estimate=CostEstimate(
                amount_usd=Decimal("0.20"),
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id="estimate-price",
            ),
        )
        await reservation.commit(
            CostEstimate(
                amount_usd=Decimal("0.27"),
                confidence=CostConfidence.EXACT,
                price_snapshot_id="actual-price",
            ),
            usage=Usage(
                input_tokens=100,
                output_tokens=40,
                total_tokens=140,
                seconds=Decimal("1.25"),
                units={"images": Decimal("2")},
            ),
            provider_request_id="provider-req-123",
        )
        commit = accounting.commits[0]
        self.assertEqual(commit["actual_amount_usd"], Decimal("0.27"))
        self.assertEqual(commit["pricing_snapshot_id"], "actual-price")
        self.assertEqual(commit["provider_request_id"], "provider-req-123")
        usage = commit["usage"]
        assert isinstance(usage, dict)
        self.assertEqual(usage["input_tokens"], (Decimal("100"), "tokens"))
        self.assertEqual(usage["seconds"], (Decimal("1.25"), "seconds"))
        self.assertEqual(usage["images"], (Decimal("2"), "units"))

    async def test_actual_overshoot_is_recorded_after_preflight(self) -> None:
        accounting = FakeAccounting()
        guard = LedgerBudgetGuard(accounting)
        reservation = await guard.reserve(
            request=request(budget=Decimal("0.30")),
            provider="alpha",
            model="reasoner-v1",
            estimate=CostEstimate(
                amount_usd=Decimal("0.20"),
                confidence=CostConfidence.ESTIMATED,
            ),
        )
        await reservation.commit(
            CostEstimate(
                amount_usd=Decimal("0.35"),
                confidence=CostConfidence.EXACT,
            )
        )
        self.assertEqual(accounting.commits[0]["actual_amount_usd"], Decimal("0.35"))

    async def test_unknown_final_cost_falls_back_to_estimate_for_reconciliation(self) -> None:
        accounting = FakeAccounting()
        guard = LedgerBudgetGuard(accounting)
        reservation = await guard.reserve(
            request=request(),
            provider="alpha",
            model="reasoner-v1",
            estimate=CostEstimate(
                amount_usd=Decimal("0.20"),
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id="estimate-price",
            ),
        )
        await reservation.commit(
            CostEstimate(
                amount_usd=None,
                confidence=CostConfidence.UNKNOWN,
            )
        )
        commit = accounting.commits[0]
        self.assertEqual(commit["actual_amount_usd"], Decimal("0.20"))
        self.assertEqual(commit["confidence"], "estimated")
        self.assertEqual(commit["pricing_snapshot_id"], "estimate-price")

    async def test_hard_budget_and_unknown_estimate_fail_before_reservation(self) -> None:
        accounting = FakeAccounting()
        guard = LedgerBudgetGuard(accounting)
        with self.assertRaises(BudgetExceededError):
            await guard.reserve(
                request=request(budget=Decimal("1")),
                provider="alpha",
                model="reasoner-v1",
                estimate=CostEstimate(
                    amount_usd=None,
                    confidence=CostConfidence.UNKNOWN,
                ),
            )
        self.assertEqual(accounting.reservations, [])

    async def test_durable_budget_rejection_is_normalized(self) -> None:
        accounting = FakeAccounting()
        accounting.reject_code = "COST_BUDGET_EXCEEDED"
        guard = LedgerBudgetGuard(accounting)
        with self.assertRaises(BudgetExceededError):
            await guard.reserve(
                request=request(),
                provider="alpha",
                model="reasoner-v1",
                estimate=CostEstimate(
                    amount_usd=Decimal("0.20"),
                    confidence=CostConfidence.ESTIMATED,
                ),
            )

    async def test_release_is_idempotent(self) -> None:
        accounting = FakeAccounting()
        guard = LedgerBudgetGuard(accounting)
        reservation = await guard.reserve(
            request=request(),
            provider="alpha",
            model="reasoner-v1",
            estimate=CostEstimate(
                amount_usd=Decimal("0.20"),
                confidence=CostConfidence.ESTIMATED,
            ),
        )
        await reservation.release(reason="not_accepted")
        await reservation.release(reason="not_accepted")
        self.assertEqual(len(accounting.releases), 1)


if __name__ == "__main__":
    unittest.main()
