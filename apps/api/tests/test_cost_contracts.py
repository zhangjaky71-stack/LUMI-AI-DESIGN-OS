from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from lumi_api.costs import (
    ActualCost,
    BudgetReservationRequest,
    CostConfidence,
    CostContext,
    UsageFact,
    decimal_amount,
    month_period_key,
)


class CostContractTests(unittest.TestCase):
    def test_decimal_amount_rejects_float(self) -> None:
        with self.assertRaisesRegex(ValueError, "COST_FLOAT_FORBIDDEN"):
            decimal_amount(0.1)  # type: ignore[arg-type]

    def test_decimal_amount_preserves_precision(self) -> None:
        value = decimal_amount("0.12345678") + decimal_amount("0.00000001")
        self.assertEqual(value, Decimal("0.12345679"))

    def test_month_period_is_utc_stable(self) -> None:
        at = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
        self.assertEqual(month_period_key(at), "month:2026-08")

    def test_actual_cost_preserves_pricing_and_usage_evidence(self) -> None:
        context = CostContext(
            organization_id=uuid4(),
            operation_id=uuid4(),
            project_id=uuid4(),
        )
        cost = ActualCost(
            context=context,
            provider="provider-a",
            model="model-a",
            amount=Decimal("0.25000000"),
            confidence=CostConfidence.EXACT,
            pricing_snapshot_id="pricing-v9",
            external_provider_request_id="req_123",
            usage=(
                UsageFact(
                    metric="input_tokens",
                    quantity=Decimal("123"),
                    unit="tokens",
                ),
            ),
        )
        self.assertEqual(cost.amount, Decimal("0.25000000"))
        self.assertEqual(cost.pricing_snapshot_id, "pricing-v9")
        self.assertEqual(cost.usage[0].quantity, Decimal("123"))

    def test_budget_reservation_rejects_negative_amount(self) -> None:
        with self.assertRaisesRegex(ValueError, "COST_RESERVATION_AMOUNT_INVALID"):
            BudgetReservationRequest(
                context=CostContext(
                    organization_id=uuid4(),
                    operation_id=uuid4(),
                ),
                provider="provider-a",
                model="model-a",
                estimated_amount=Decimal("-0.01"),
            )


if __name__ == "__main__":
    unittest.main()
