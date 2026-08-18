from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session


class BillingReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    from_time: datetime
    to_time: datetime
    provider_cost: Decimal
    customer_billed: Decimal
    customer_collected: Decimal
    gross_margin_on_billed: Decimal


class PostgresBillingReconciliationService:
    """Read-only comparison; NODE-27 cost facts remain authoritative and untouched."""

    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    def summarize(
        self,
        *,
        from_time: datetime,
        to_time: datetime,
        currency: str = "USD",
    ) -> BillingReconciliation:
        if from_time.tzinfo is None or to_time.tzinfo is None or from_time >= to_time:
            raise ValueError("BILLING_RECONCILIATION_TIME_RANGE_INVALID")
        if len(currency) != 3 or not currency.isascii() or not currency.isupper():
            raise ValueError("BILLING_RECONCILIATION_CURRENCY_INVALID")
        cost = self.session.execute(
            text(
                """
                SELECT COALESCE(sum(amount),0) AS amount
                FROM cost_ledger
                WHERE organization_id=:organization_id
                  AND occurred_at >= :from_time AND occurred_at < :to_time
                  AND currency=:currency
                  AND cost_basis='provider_cost'
                  AND entry_type IN ('actual_cost','adjustment','reversal')
                """
            ),
            {
                "organization_id": self.organization_id,
                "from_time": from_time,
                "to_time": to_time,
                "currency": currency,
            },
        ).scalar_one()
        invoice = self.session.execute(
            text(
                """
                SELECT
                    COALESCE(sum(amount_due),0) AS billed,
                    COALESCE(sum(amount_due) FILTER (
                        WHERE lower(status) IN ('paid','succeeded','settled')
                    ),0) AS collected
                FROM billing_invoice_refs
                WHERE organization_id=:organization_id
                  AND created_at >= :from_time AND created_at < :to_time
                  AND currency=:currency
                """
            ),
            {
                "organization_id": self.organization_id,
                "from_time": from_time,
                "to_time": to_time,
                "currency": currency,
            },
        ).mappings().one()
        provider_cost = Decimal(cost)
        customer_billed = Decimal(invoice["billed"])
        customer_collected = Decimal(invoice["collected"])
        return BillingReconciliation(
            organization_id=self.organization_id,
            currency=currency,
            from_time=from_time,
            to_time=to_time,
            provider_cost=provider_cost,
            customer_billed=customer_billed,
            customer_collected=customer_collected,
            gross_margin_on_billed=customer_billed - provider_cost,
        )
