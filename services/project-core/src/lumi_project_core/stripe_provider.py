from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .billing import (
    BillingError,
    HostedSession,
    NormalizedPaymentEvent,
    PlanVersion,
    ProviderSubscription,
)

StripeTransport = Callable[
    [str, str, list[tuple[str, str]] | None, str, str | None],
    dict[str, object],
]


@dataclass(frozen=True, slots=True)
class StripeProviderConfig:
    secret_key: str
    webhook_secret: str
    price_ids_by_plan_version: Mapping[str, str]
    checkout_success_url: str
    checkout_cancel_url: str
    portal_return_url: str
    expected_livemode: bool
    webhook_tolerance_seconds: int = 300
    api_base: str = "https://api.stripe.com/v1"
    api_version: str = "2026-02-25.clover"

    def __post_init__(self) -> None:
        expected_prefix = "sk_live_" if self.expected_livemode else "sk_test_"
        if not self.secret_key.startswith(expected_prefix):
            raise BillingError("BILLING_STRIPE_MODE_KEY_MISMATCH", 500)
        if not self.webhook_secret.startswith("whsec_"):
            raise BillingError("BILLING_STRIPE_WEBHOOK_SECRET_INVALID", 500)
        if self.webhook_tolerance_seconds <= 0:
            raise BillingError("BILLING_STRIPE_WEBHOOK_TOLERANCE_INVALID", 500)
        if not self.api_version.strip():
            raise BillingError("BILLING_STRIPE_API_VERSION_INVALID", 500)
        if not self.price_ids_by_plan_version:
            raise BillingError("BILLING_STRIPE_PRICE_MAP_EMPTY", 500)
        for plan_version_id, price_id in self.price_ids_by_plan_version.items():
            if not plan_version_id.strip() or not price_id.startswith("price_"):
                raise BillingError("BILLING_STRIPE_PRICE_MAP_INVALID", 500)
        for value in (
            self.checkout_success_url,
            self.checkout_cancel_url,
            self.portal_return_url,
        ):
            if not value.startswith("https://"):
                raise BillingError("BILLING_STRIPE_RETURN_URL_INVALID", 500)


class StripePaymentProvider:
    """Stripe-hosted billing adapter with server-owned prices and verified events."""

    name = "STRIPE"

    def __init__(
        self,
        config: StripeProviderConfig,
        *,
        transport: StripeTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._transport = transport or self._default_transport
        self._now = now

    def validate_plan_price(self, plan: PlanVersion) -> None:
        price_id = self._config.price_ids_by_plan_version.get(plan.plan_version_id)
        if not price_id:
            raise BillingError("BILLING_STRIPE_PRICE_NOT_CONFIGURED", 409)
        price = self._api("GET", f"/prices/{quote(price_id, safe='')}", None)
        if price.get("active") is not True:
            raise BillingError("BILLING_STRIPE_PRICE_INACTIVE", 409)
        if price.get("livemode") is not self._config.expected_livemode:
            raise BillingError("BILLING_STRIPE_PRICE_MODE_MISMATCH", 409)
        if _optional_string(price.get("type")) != "recurring":
            raise BillingError("BILLING_STRIPE_PRICE_NOT_RECURRING", 409)
        if _optional_string(price.get("billing_scheme")) != "per_unit":
            raise BillingError("BILLING_STRIPE_PRICE_BILLING_SCHEME_UNSUPPORTED", 409)
        currency = _required_string(price, "currency", "BILLING_STRIPE_PRICE_INVALID").upper()
        if currency != plan.currency or currency != "USD":
            raise BillingError("BILLING_STRIPE_PRICE_CURRENCY_MISMATCH", 409)
        unit_amount = price.get("unit_amount")
        if isinstance(unit_amount, bool) or not isinstance(unit_amount, int) or unit_amount < 0:
            raise BillingError("BILLING_STRIPE_PRICE_AMOUNT_INVALID", 409)
        if unit_amount * 10_000 != plan.price_microusd:
            raise BillingError("BILLING_STRIPE_PRICE_AMOUNT_MISMATCH", 409)
        recurring = _mapping(price.get("recurring"))
        interval = _optional_string(recurring.get("interval"))
        expected_interval = "month" if plan.billing_interval == "MONTH" else "year"
        if interval != expected_interval or recurring.get("interval_count") != 1:
            raise BillingError("BILLING_STRIPE_PRICE_INTERVAL_MISMATCH", 409)
        if _optional_string(recurring.get("usage_type")) != "licensed":
            raise BillingError("BILLING_STRIPE_PRICE_USAGE_TYPE_UNSUPPORTED", 409)

    def create_customer(self, organization_id: str, billing_email: str | None) -> str:
        fields: list[tuple[str, str]] = [("metadata[organization_id]", organization_id)]
        if billing_email:
            fields.append(("email", billing_email))
        body = self._api(
            "POST",
            "/customers",
            fields,
            idempotency_key=f"lumi-customer:{organization_id}"[:255],
        )
        return _required_string(body, "id", "BILLING_STRIPE_CUSTOMER_INVALID")

    def create_checkout(self, customer_ref: str, plan: PlanVersion) -> HostedSession:
        price_id = self._config.price_ids_by_plan_version.get(plan.plan_version_id)
        if not price_id:
            raise BillingError("BILLING_STRIPE_PRICE_NOT_CONFIGURED", 409)
        fields = [
            ("mode", "subscription"),
            ("customer", customer_ref),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", "1"),
            ("success_url", self._config.checkout_success_url),
            ("cancel_url", self._config.checkout_cancel_url),
            ("metadata[plan_version_id]", plan.plan_version_id),
            ("subscription_data[metadata][plan_version_id]", plan.plan_version_id),
        ]
        customer = self._api("GET", f"/customers/{quote(customer_ref, safe='')}", None)
        customer_metadata = _mapping(customer.get("metadata"))
        organization_id = _optional_string(customer_metadata.get("organization_id"))
        if not organization_id:
            raise BillingError("BILLING_STRIPE_CUSTOMER_ORGANIZATION_MISSING", 409)
        fields.extend(
            [
                ("metadata[organization_id]", organization_id),
                ("subscription_data[metadata][organization_id]", organization_id),
            ]
        )
        body = self._api("POST", "/checkout/sessions", fields)
        return HostedSession(
            provider=self.name,
            session_ref=_required_string(body, "id", "BILLING_STRIPE_CHECKOUT_INVALID"),
            url=_required_string(body, "url", "BILLING_STRIPE_CHECKOUT_INVALID"),
        )

    def create_portal_session(self, customer_ref: str) -> HostedSession:
        body = self._api(
            "POST",
            "/billing_portal/sessions",
            [("customer", customer_ref), ("return_url", self._config.portal_return_url)],
        )
        return HostedSession(
            provider=self.name,
            session_ref=_required_string(body, "id", "BILLING_STRIPE_PORTAL_INVALID"),
            url=_required_string(body, "url", "BILLING_STRIPE_PORTAL_INVALID"),
        )

    def get_subscription(self, provider_subscription_ref: str) -> ProviderSubscription:
        body = self._api(
            "GET", f"/subscriptions/{quote(provider_subscription_ref, safe='')}", None
        )
        return self._provider_subscription(body)

    def cancel_subscription(self, provider_subscription_ref: str) -> ProviderSubscription:
        body = self._api(
            "POST",
            f"/subscriptions/{quote(provider_subscription_ref, safe='')}",
            [("cancel_at_period_end", "true")],
        )
        return self._provider_subscription(body)

    def verify_webhook(
        self, raw_body: bytes, signature: str
    ) -> tuple[NormalizedPaymentEvent, str]:
        timestamp, signatures = _parse_signature_header(signature)
        now = int(self._now())
        if abs(now - timestamp) > self._config.webhook_tolerance_seconds:
            raise BillingError("BILLING_WEBHOOK_SIGNATURE_STALE", 401)
        signed_payload = str(timestamp).encode("ascii") + b"." + raw_body
        expected = hmac.new(
            self._config.webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        if not signatures or not any(hmac.compare_digest(expected, item) for item in signatures):
            raise BillingError("BILLING_WEBHOOK_SIGNATURE_INVALID", 401)
        try:
            event = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BillingError("BILLING_WEBHOOK_INVALID") from error
        if not isinstance(event, dict):
            raise BillingError("BILLING_WEBHOOK_INVALID")
        livemode = event.get("livemode")
        if not isinstance(livemode, bool) or livemode is not self._config.expected_livemode:
            raise BillingError("BILLING_STRIPE_EVENT_MODE_MISMATCH", 409)
        event_api_version = _optional_string(event.get("api_version"))
        if event_api_version != self._config.api_version:
            raise BillingError("BILLING_STRIPE_EVENT_API_VERSION_MISMATCH", 409)
        normalized = self._normalize_event(event)
        return normalized, hashlib.sha256(raw_body).hexdigest()

    def _normalize_event(self, event: dict[str, object]) -> NormalizedPaymentEvent:
        event_id = _required_string(event, "id", "BILLING_WEBHOOK_INVALID")
        stripe_type = _required_string(event, "type", "BILLING_WEBHOOK_INVALID")
        data = _mapping(event.get("data"))
        obj = _mapping(data.get("object"))

        if stripe_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            metadata = _mapping(obj.get("metadata"))
            organization_id, plan_version_id = _billing_identity(metadata)
            state = "CANCELLED" if stripe_type.endswith(".deleted") else _subscription_state(obj)
            return NormalizedPaymentEvent(
                provider=self.name,
                provider_event_id=event_id,
                event_type=(
                    "SUBSCRIPTION_CREATED"
                    if stripe_type.endswith(".created")
                    else "SUBSCRIPTION_CANCELLED"
                    if stripe_type.endswith(".deleted")
                    else "SUBSCRIPTION_UPDATED"
                ),
                organization_id=organization_id,
                plan_version_id=plan_version_id,
                customer_ref=_optional_string(obj.get("customer")),
                subscription_ref=_required_string(
                    obj, "id", "BILLING_WEBHOOK_SUBSCRIPTION_INCOMPLETE"
                ),
                subscription_state=state,
                period_start=_stripe_time(obj.get("current_period_start")),
                period_end=_stripe_time(obj.get("current_period_end")),
            )

        if stripe_type in {"invoice.paid", "invoice.payment_failed"}:
            metadata, subscription_ref = _invoice_subscription_identity(obj)
            organization_id, plan_version_id = _billing_identity(metadata)
            amount_due = obj.get("amount_due")
            if isinstance(amount_due, bool) or not isinstance(amount_due, int) or amount_due < 0:
                raise BillingError("BILLING_WEBHOOK_INVOICE_INCOMPLETE")
            currency = _required_string(obj, "currency", "BILLING_WEBHOOK_INVOICE_INCOMPLETE")
            if currency.lower() != "usd":
                raise BillingError("BILLING_STRIPE_CURRENCY_UNSUPPORTED", 409)
            return NormalizedPaymentEvent(
                provider=self.name,
                provider_event_id=event_id,
                event_type="INVOICE_PAID" if stripe_type == "invoice.paid" else "INVOICE_PAYMENT_FAILED",
                organization_id=organization_id,
                plan_version_id=plan_version_id,
                customer_ref=_optional_string(obj.get("customer")),
                subscription_ref=subscription_ref,
                invoice_ref=_required_string(obj, "id", "BILLING_WEBHOOK_INVOICE_INCOMPLETE"),
                amount_due_microusd=amount_due * 10_000,
                currency=currency.upper(),
                hosted_invoice_url=_optional_string(obj.get("hosted_invoice_url")),
            )

        raise BillingError("BILLING_STRIPE_EVENT_UNSUPPORTED", 400)

    def _provider_subscription(self, body: dict[str, object]) -> ProviderSubscription:
        return ProviderSubscription(
            provider_subscription_ref=_required_string(
                body, "id", "BILLING_STRIPE_SUBSCRIPTION_INVALID"
            ),
            state=_subscription_state(body),
            cancel_at_period_end=body.get("cancel_at_period_end") is True,
            current_period_start=_stripe_time(body.get("current_period_start")),
            current_period_end=_stripe_time(body.get("current_period_end")),
        )

    def _api(
        self,
        method: str,
        path: str,
        fields: list[tuple[str, str]] | None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        try:
            return self._transport(
                method,
                path,
                fields,
                self._config.secret_key,
                idempotency_key,
            )
        except BillingError:
            raise
        except Exception as error:  # pragma: no cover
            raise BillingError("BILLING_STRIPE_UNAVAILABLE", 503) from error

    def _default_transport(
        self,
        method: str,
        path: str,
        fields: list[tuple[str, str]] | None,
        secret_key: str,
        idempotency_key: str | None,
    ) -> dict[str, object]:
        url = self._config.api_base.rstrip("/") + path
        data = urlencode(fields).encode("utf-8") if fields is not None else None
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "lumi-ai-design-os/stripe-adapter",
            "Stripe-Version": self._config.api_version,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed HTTPS API base
                payload = response.read()
        except HTTPError as error:
            payload = error.read()
            code = _stripe_error_code(payload) or "BILLING_STRIPE_REQUEST_FAILED"
            raise BillingError(code, 502) from error
        except (URLError, TimeoutError) as error:
            raise BillingError("BILLING_STRIPE_UNAVAILABLE", 503) from error
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BillingError("BILLING_STRIPE_RESPONSE_INVALID", 502) from error
        if not isinstance(decoded, dict):
            raise BillingError("BILLING_STRIPE_RESPONSE_INVALID", 502)
        return decoded


def _parse_signature_header(value: str) -> tuple[int, tuple[str, ...]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for item in value.split(","):
        key, separator, raw = item.strip().partition("=")
        if not separator:
            continue
        if key == "t":
            try:
                timestamp = int(raw)
            except ValueError as error:
                raise BillingError("BILLING_WEBHOOK_SIGNATURE_INVALID", 401) from error
        elif key == "v1" and raw:
            signatures.append(raw)
    if timestamp is None:
        raise BillingError("BILLING_WEBHOOK_SIGNATURE_INVALID", 401)
    return timestamp, tuple(signatures)


def _subscription_state(value: Mapping[str, object]) -> str:
    if value.get("cancel_at_period_end") is True:
        return "CANCEL_AT_PERIOD_END"
    status = _optional_string(value.get("status"))
    mapping = {
        "trialing": "TRIALING",
        "active": "ACTIVE",
        "past_due": "PAST_DUE",
        "canceled": "CANCELLED",
        "incomplete": "INCOMPLETE",
        "incomplete_expired": "INCOMPLETE",
        "unpaid": "PAST_DUE",
        "paused": "PAST_DUE",
    }
    state = mapping.get(status or "")
    if state is None:
        raise BillingError("BILLING_STRIPE_SUBSCRIPTION_STATE_UNSUPPORTED", 409)
    return state


def _invoice_subscription_identity(
    invoice: Mapping[str, object],
) -> tuple[Mapping[str, object], str | None]:
    parent = _mapping(invoice.get("parent"))
    details = _mapping(parent.get("subscription_details"))
    if not details:
        details = _mapping(invoice.get("subscription_details"))
    metadata = _mapping(details.get("metadata"))
    subscription_ref = _optional_string(details.get("subscription"))
    subscription_ref = subscription_ref or _optional_string(invoice.get("subscription"))
    if metadata:
        return metadata, subscription_ref
    lines = _mapping(invoice.get("lines"))
    data = lines.get("data")
    if isinstance(data, list):
        for line in data:
            line_mapping = _mapping(line)
            candidate = _mapping(line_mapping.get("metadata"))
            if candidate.get("organization_id") and candidate.get("plan_version_id"):
                return candidate, subscription_ref
    raise BillingError("BILLING_WEBHOOK_BILLING_IDENTITY_MISSING", 409)


def _billing_identity(metadata: Mapping[str, object]) -> tuple[str, str]:
    organization_id = _optional_string(metadata.get("organization_id"))
    plan_version_id = _optional_string(metadata.get("plan_version_id"))
    if not organization_id or not plan_version_id:
        raise BillingError("BILLING_WEBHOOK_BILLING_IDENTITY_MISSING", 409)
    return organization_id, plan_version_id


def _stripe_time(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise BillingError("BILLING_STRIPE_TIMESTAMP_INVALID", 409)
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _required_string(value: Mapping[str, object], key: str, code: str) -> str:
    result = _optional_string(value.get(key))
    if result is None:
        raise BillingError(code, 502 if code.startswith("BILLING_STRIPE_") else 400)
    return result


def _stripe_error_code(payload: bytes) -> str | None:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    error = decoded.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    if isinstance(code, str) and code:
        safe = "".join(character if character.isalnum() else "_" for character in code.upper())
        return f"BILLING_STRIPE_{safe}"[:128]
    return None
