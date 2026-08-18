from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from .contracts import (
    CheckoutSession,
    InvalidWebhook,
    NormalizedPaymentEvent,
    PlanVersionRecord,
    PortalSession,
    SubscriptionState,
)


class MockPaymentProvider:
    """Deterministic hosted-payment adapter for tests and sandbox acceptance only."""

    name = "mock"

    def __init__(self, webhook_secret: str) -> None:
        if not webhook_secret:
            raise ValueError("BILLING_MOCK_WEBHOOK_SECRET_REQUIRED")
        self._secret = webhook_secret.encode("utf-8")

    def create_customer(self, *, organization_id: UUID) -> str:
        return f"mock_cus_{organization_id.hex}"

    def create_checkout(
        self,
        *,
        organization_id: UUID,
        provider_customer_ref: str,
        plan_version: PlanVersionRecord,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        _require_https_or_local(success_url)
        _require_https_or_local(cancel_url)
        session_ref = f"mock_checkout_{uuid4().hex}"
        return CheckoutSession(
            provider=self.name,
            provider_session_ref=session_ref,
            url=(
                "https://payments.lumi.invalid/checkout/"
                f"{session_ref}?customer={provider_customer_ref}&plan_version={plan_version.id}"
            ),
        )

    def create_portal_session(
        self, *, provider_customer_ref: str, return_url: str
    ) -> PortalSession:
        _require_https_or_local(return_url)
        session_ref = f"mock_portal_{uuid4().hex}"
        return PortalSession(
            provider=self.name,
            url=(
                "https://payments.lumi.invalid/portal/"
                f"{session_ref}?customer={provider_customer_ref}"
            ),
        )

    def sign(self, body: bytes) -> str:
        return hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def verify_webhook(self, *, body: bytes, signature: str) -> NormalizedPaymentEvent:
        expected = self.sign(body)
        if not hmac.compare_digest(expected, signature):
            raise InvalidWebhook("BILLING_WEBHOOK_SIGNATURE_INVALID")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidWebhook("BILLING_WEBHOOK_JSON_INVALID") from exc
        if not isinstance(payload, dict):
            raise InvalidWebhook("BILLING_WEBHOOK_OBJECT_REQUIRED")
        forbidden = {"card_number", "pan", "cvc", "cvv", "track_data"}
        if forbidden.intersection(_flatten_keys(payload)):
            raise InvalidWebhook("BILLING_WEBHOOK_CARD_DATA_FORBIDDEN")
        try:
            return NormalizedPaymentEvent(
                provider=self.name,
                provider_event_id=str(payload["id"]),
                event_type=str(payload["type"]),
                organization_id=UUID(str(payload["organization_id"])),
                occurred_at=_datetime(payload["occurred_at"]),
                subscription_ref=_optional_str(payload.get("subscription_ref")),
                plan_key=_optional_str(payload.get("plan_key")),
                plan_version=_optional_int(payload.get("plan_version")),
                subscription_state=(
                    SubscriptionState(str(payload["subscription_state"]))
                    if payload.get("subscription_state") is not None
                    else None
                ),
                current_period_start=_optional_datetime(payload.get("current_period_start")),
                current_period_end=_optional_datetime(payload.get("current_period_end")),
                invoice_ref=_optional_str(payload.get("invoice_ref")),
                invoice_status=_optional_str(payload.get("invoice_status")),
                invoice_amount=_optional_decimal(payload.get("invoice_amount")),
                currency=_optional_str(payload.get("currency")),
                hosted_invoice_url=_optional_str(payload.get("hosted_invoice_url")),
                credit_grant=_optional_decimal(payload.get("credit_grant")),
                metadata=_safe_metadata(payload.get("metadata")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidWebhook("BILLING_WEBHOOK_CONTRACT_INVALID") from exc


def _require_https_or_local(value: str) -> None:
    if value.startswith("https://") or value.startswith("http://localhost"):
        return
    raise ValueError("BILLING_HOSTED_RETURN_URL_INVALID")


def _datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else _datetime(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise ValueError("float forbidden")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non-finite decimal")
    return result


def _safe_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("metadata object required")
    if len(value) > 32:
        raise ValueError("metadata too large")
    return {str(key): item for key, item in value.items()}


def _flatten_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).casefold())
            keys.update(_flatten_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_flatten_keys(item))
    return keys
