from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text

from lumi_api.domain.ids import new_uuid7

from .contracts import BillingConflict, NormalizedPaymentEvent, PaymentEventStatus
from .repository import PostgresBillingRepository as _BasePostgresBillingRepository


class PostgresBillingRepository(_BasePostgresBillingRepository):
    """Production repository hardening for idempotent payment-event claims."""

    def claim_payment_event(
        self, event: NormalizedPaymentEvent, *, body_sha256: str
    ) -> PaymentEventStatus:
        self._assert_org(event.organization_id)
        with self._transaction():
            self.session.execute(
                text(
                    """
                    INSERT INTO billing_payment_events (
                        id, organization_id, provider, provider_event_id, event_type,
                        body_sha256, status, occurred_at, created_at, updated_at
                    ) VALUES (
                        :id, :organization_id, :provider, :provider_event_id, :event_type,
                        :body_sha256, 'RECEIVED', :occurred_at, :now, :now
                    )
                    ON CONFLICT (provider, provider_event_id) DO NOTHING
                    """
                ),
                {
                    "id": new_uuid7(),
                    "organization_id": self.organization_id,
                    "provider": event.provider,
                    "provider_event_id": event.provider_event_id,
                    "event_type": event.event_type,
                    "body_sha256": body_sha256,
                    "occurred_at": event.occurred_at,
                    "now": datetime.now(UTC),
                },
            )
        row = self.session.execute(
            text(
                """
                SELECT organization_id, status, body_sha256
                FROM billing_payment_events
                WHERE provider=:provider AND provider_event_id=:provider_event_id
                """
            ),
            {"provider": event.provider, "provider_event_id": event.provider_event_id},
        ).mappings().one_or_none()
        if row is None or row["organization_id"] != self.organization_id:
            raise BillingConflict("BILLING_PAYMENT_EVENT_CLAIM_FAILED")
        if str(row["body_sha256"]) != body_sha256:
            raise BillingConflict("BILLING_PAYMENT_EVENT_BODY_CONFLICT")
        return PaymentEventStatus(str(row["status"]))
