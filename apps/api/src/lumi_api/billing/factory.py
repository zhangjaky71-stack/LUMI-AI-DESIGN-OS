from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator
from uuid import UUID

from sqlalchemy.orm import Session

from .contracts import InvalidWebhook, PaymentEventStatus, PaymentProvider
from .repository import PostgresBillingRepository
from .service import BillingService


class PostgresBillingServiceFactory:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        provider: PaymentProvider,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider

    @contextmanager
    def __call__(self, organization_id: UUID) -> Iterator[BillingService]:
        session = self.session_factory()
        try:
            yield BillingService(
                PostgresBillingRepository(session, organization_id),
                self.provider,
            )
        finally:
            session.close()

    def handle_webhook(self, *, body: bytes, signature: str) -> PaymentEventStatus:
        event = self.provider.verify_webhook(body=body, signature=signature)
        if event.provider != self.provider.name:
            raise InvalidWebhook("BILLING_WEBHOOK_PROVIDER_MISMATCH")
        with self(event.organization_id) as service:
            return service.apply_verified_payment_event(
                event,
                body_sha256=service.body_hash(body),
            )
