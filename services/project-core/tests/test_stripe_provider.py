from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from lumi_project_core.billing import BillingError, PlanVersion
from lumi_project_core.stripe_provider import StripePaymentProvider, StripeProviderConfig


SECRET = "whsec_test_secret"
API_VERSION = "2026-02-25.clover"


def config(*, live: bool = False) -> StripeProviderConfig:
    return StripeProviderConfig(
        secret_key="sk_live_example" if live else "sk_test_example",
        webhook_secret=SECRET,
        price_ids_by_plan_version={"pro-v1": "price_server_owned"},
        checkout_success_url="https://app.example.test/billing/success",
        checkout_cancel_url="https://app.example.test/billing/cancel",
        portal_return_url="https://app.example.test/settings/billing",
        expected_livemode=live,
        api_version=API_VERSION,
    )


def plan() -> PlanVersion:
    return PlanVersion(
        plan_id="pro",
        plan_version_id="pro-v1",
        version=1,
        name="Pro",
        currency="USD",
        price_microusd=2_000_000,
        billing_interval="MONTH",
        monthly_credit_grant=500,
        entitlements={"generations": 100},
    )


def signature(raw: bytes, timestamp: int, *, secret: str = SECRET) -> str:
    digest = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1=invalid,v1={digest}"


def stripe_price(*, live: bool = False, unit_amount: int = 200) -> dict[str, object]:
    return {
        "id": "price_server_owned",
        "active": True,
        "livemode": live,
        "type": "recurring",
        "billing_scheme": "per_unit",
        "currency": "usd",
        "unit_amount": unit_amount,
        "recurring": {
            "interval": "month",
            "interval_count": 1,
            "usage_type": "licensed",
        },
    }


def test_mode_key_must_match_environment() -> None:
    with pytest.raises(BillingError, match="BILLING_STRIPE_MODE_KEY_MISMATCH"):
        StripeProviderConfig(
            secret_key="sk_test_wrong_for_prod",
            webhook_secret=SECRET,
            price_ids_by_plan_version={"pro-v1": "price_x"},
            checkout_success_url="https://app.example.test/success",
            checkout_cancel_url="https://app.example.test/cancel",
            portal_return_url="https://app.example.test/billing",
            expected_livemode=True,
        )


def test_customer_creation_uses_stable_idempotency_key() -> None:
    calls: list[tuple[str, str, list[tuple[str, str]] | None, str | None]] = []

    def transport(method, path, fields, _secret, idempotency_key):
        calls.append((method, path, fields, idempotency_key))
        return {"id": "cus_1"}

    provider = StripePaymentProvider(config(), transport=transport)
    assert provider.create_customer("org-1", "billing@example.test") == "cus_1"
    assert calls == [
        (
            "POST",
            "/customers",
            [
                ("metadata[organization_id]", "org-1"),
                ("email", "billing@example.test"),
            ],
            "lumi-customer:org-1",
        )
    ]


def test_plan_price_reconciliation_accepts_exact_recurring_contract() -> None:
    def transport(method, path, _fields, _secret, _idempotency_key):
        assert method == "GET"
        assert path == "/prices/price_server_owned"
        return stripe_price()

    StripePaymentProvider(config(), transport=transport).validate_plan_price(plan())


def test_plan_price_reconciliation_rejects_amount_drift() -> None:
    provider = StripePaymentProvider(
        config(), transport=lambda *_: stripe_price(unit_amount=201)
    )
    with pytest.raises(BillingError, match="BILLING_STRIPE_PRICE_AMOUNT_MISMATCH"):
        provider.validate_plan_price(plan())


def test_plan_price_reconciliation_rejects_mode_drift() -> None:
    provider = StripePaymentProvider(config(), transport=lambda *_: stripe_price(live=True))
    with pytest.raises(BillingError, match="BILLING_STRIPE_PRICE_MODE_MISMATCH"):
        provider.validate_plan_price(plan())


def test_checkout_uses_server_owned_price_and_subscription_metadata() -> None:
    calls: list[tuple[str, str, list[tuple[str, str]] | None]] = []

    def transport(method, path, fields, _secret, _idempotency_key):
        calls.append((method, path, fields))
        if method == "GET":
            return {"id": "cus_1", "metadata": {"organization_id": "org-1"}}
        return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}

    provider = StripePaymentProvider(config(), transport=transport)
    session = provider.create_checkout("cus_1", plan())
    assert session.session_ref == "cs_1"
    posted = dict(calls[-1][2] or [])
    assert posted["mode"] == "subscription"
    assert posted["line_items[0][price]"] == "price_server_owned"
    assert posted["subscription_data[metadata][organization_id]"] == "org-1"
    assert posted["subscription_data[metadata][plan_version_id]"] == "pro-v1"
    assert not any("amount" in key for key in posted)


def test_unmapped_plan_cannot_create_checkout() -> None:
    provider = StripePaymentProvider(
        config(), transport=lambda *_: {"metadata": {"organization_id": "org-1"}}
    )
    other = PlanVersion(
        plan_id="enterprise",
        plan_version_id="enterprise-v1",
        version=1,
        name="Enterprise",
        currency="USD",
        price_microusd=1,
        billing_interval="MONTH",
        monthly_credit_grant=0,
        entitlements={},
    )
    with pytest.raises(BillingError, match="BILLING_STRIPE_PRICE_NOT_CONFIGURED"):
        provider.create_checkout("cus_1", other)


def test_webhook_accepts_any_valid_v1_and_rejects_stale_timestamp() -> None:
    now = 1_800_000_000
    raw = json.dumps(
        {
            "id": "evt_1",
            "type": "customer.subscription.updated",
            "api_version": API_VERSION,
            "livemode": False,
            "data": {
                "object": {
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": now - 100,
                    "current_period_end": now + 100,
                    "metadata": {
                        "organization_id": "11111111-1111-1111-1111-111111111111",
                        "plan_version_id": "pro-v1",
                    },
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    provider = StripePaymentProvider(config(), transport=lambda *_: {}, now=lambda: now)
    event, payload_hash = provider.verify_webhook(raw, signature(raw, now))
    assert event.event_type == "SUBSCRIPTION_UPDATED"
    assert event.subscription_state == "ACTIVE"
    assert payload_hash == hashlib.sha256(raw).hexdigest()

    with pytest.raises(BillingError, match="BILLING_WEBHOOK_SIGNATURE_STALE"):
        provider.verify_webhook(raw, signature(raw, now - 301))


def test_webhook_api_version_mismatch_fails_closed() -> None:
    now = 1_800_000_000
    raw = json.dumps(
        {
            "id": "evt_old_api",
            "type": "customer.subscription.updated",
            "api_version": "2025-12-15.clover",
            "livemode": False,
            "data": {"object": {}},
        }
    ).encode()
    provider = StripePaymentProvider(config(), transport=lambda *_: {}, now=lambda: now)
    with pytest.raises(BillingError, match="BILLING_STRIPE_EVENT_API_VERSION_MISMATCH"):
        provider.verify_webhook(raw, signature(raw, now))


def test_invalid_signature_is_rejected_before_json_parse() -> None:
    now = 1_800_000_000
    provider = StripePaymentProvider(config(), transport=lambda *_: {}, now=lambda: now)
    with pytest.raises(BillingError, match="BILLING_WEBHOOK_SIGNATURE_INVALID"):
        provider.verify_webhook(b"not-json", f"t={now},v1=wrong")


def test_livemode_mismatch_fails_closed() -> None:
    now = 1_800_000_000
    raw = json.dumps(
        {
            "id": "evt_live",
            "type": "invoice.paid",
            "api_version": API_VERSION,
            "livemode": True,
            "data": {"object": {}},
        }
    ).encode()
    provider = StripePaymentProvider(config(), transport=lambda *_: {}, now=lambda: now)
    with pytest.raises(BillingError, match="BILLING_STRIPE_EVENT_MODE_MISMATCH"):
        provider.verify_webhook(raw, signature(raw, now))


def test_invoice_paid_normalizes_subscription_metadata_and_microusd() -> None:
    now = 1_800_000_000
    raw = json.dumps(
        {
            "id": "evt_invoice",
            "type": "invoice.paid",
            "api_version": API_VERSION,
            "livemode": False,
            "data": {
                "object": {
                    "id": "in_1",
                    "customer": "cus_1",
                    "amount_due": 1234,
                    "currency": "usd",
                    "hosted_invoice_url": "https://invoice.stripe.com/i/in_1",
                    "parent": {
                        "subscription_details": {
                            "subscription": "sub_1",
                            "metadata": {
                                "organization_id": "11111111-1111-1111-1111-111111111111",
                                "plan_version_id": "pro-v1",
                            },
                        }
                    },
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    provider = StripePaymentProvider(config(), transport=lambda *_: {}, now=lambda: now)
    event, _ = provider.verify_webhook(raw, signature(raw, now))
    assert event.event_type == "INVOICE_PAID"
    assert event.amount_due_microusd == 12_340_000
    assert event.currency == "USD"
    assert event.subscription_ref == "sub_1"
