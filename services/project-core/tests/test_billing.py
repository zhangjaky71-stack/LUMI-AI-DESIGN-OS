from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json

import pytest

from lumi_project_core.billing import (
    BillingActor,
    BillingEngine,
    BillingError,
    CreditLedgerEntry,
    InMemoryBillingRepository,
    MockPaymentProvider,
    PlanVersion,
    PricingPolicyVersion,
    StaticProviderCostPort,
    UsagePricingRule,
)


def setup_engine(
    provider_costs: dict[str, int | None] | None = None,
) -> tuple[BillingEngine, InMemoryBillingRepository, MockPaymentProvider, BillingActor]:
    repo = InMemoryBillingRepository()
    provider = MockPaymentProvider()
    actor = BillingActor(
        "owner-1",
        "org-1",
        frozenset({"billing.read", "billing.manage"}),
        "owner@example.com",
    )
    engine = BillingEngine(
        repository=repo,
        payment_provider=provider,
        provider_costs=StaticProviderCostPort(provider_costs),
    )
    engine.publish_plan_version(
        actor,
        PlanVersion(
            "pro",
            "pro-v1",
            1,
            "Pro",
            "USD",
            49_000_000,
            "MONTH",
            1000,
            {"video_enabled": True, "max_concurrent_generations": 4, "team_seats": 5},
        ),
    )
    engine.publish_plan_version(
        actor,
        PlanVersion(
            "pro",
            "pro-v2",
            2,
            "Pro",
            "USD",
            59_000_000,
            "MONTH",
            1200,
            {"video_enabled": True, "max_concurrent_generations": 6, "team_seats": 8},
        ),
    )
    engine.publish_pricing_policy(
        actor,
        PricingPolicyVersion(
            "default",
            1,
            (
                UsagePricingRule("image.standard", 10),
                UsagePricingRule("video.second", 3, 20_000),
            ),
        ),
    )
    return engine, repo, provider, actor


def subscription_event(
    event_id: str = "evt-sub-1",
    plan: str = "pro-v1",
    state: str = "ACTIVE",
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "SUBSCRIPTION_CREATED" if event_id == "evt-sub-1" else "SUBSCRIPTION_UPDATED",
            "organization_id": "org-1",
            "plan_version_id": plan,
            "subscription_ref": "mock_sub_1",
            "subscription_state": state,
            "period_start": "2026-08-01T00:00:00Z",
            "period_end": "2026-09-01T00:00:00Z",
        }
    ).encode()


def invoice_event(
    event_id: str = "evt-invoice-1",
    invoice_ref: str = "inv-1",
    plan: str = "pro-v1",
    amount: int = 49_000_000,
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "INVOICE_PAID",
            "organization_id": "org-1",
            "plan_version_id": plan,
            "invoice_ref": invoice_ref,
            "amount_due_microusd": amount,
            "currency": "USD",
            "hosted_invoice_url": f"https://invoice.mock.invalid/{invoice_ref}",
        }
    ).encode()


def grant(repo: InMemoryBillingRepository, credits: int = 100) -> None:
    repo.append_credit(
        CreditLedgerEntry(
            "grant-1",
            "org-1",
            "GRANT",
            credits,
            "TEST",
            "grant",
            None,
            "grant-once",
            "2026-08-15T00:00:00Z",
        )
    )


def test_plan_version_is_immutable_and_subscription_remains_pinned() -> None:
    engine, repo, provider, actor = setup_engine()
    engine.process_webhook(subscription_event(), provider.signature)
    subscription = repo.get_subscription("org-1")
    assert subscription is not None and subscription.plan_version_id == "pro-v1"
    current_plan = engine.summary(actor).current_plan
    assert current_plan is not None and current_plan.plan_version_id == "pro-v1"
    existing = repo.get_plan_version("pro-v1")
    assert existing is not None
    with pytest.raises(BillingError, match="IMMUTABLE"):
        engine.publish_plan_version(actor, existing)


def test_duplicate_webhook_does_not_double_grant_credits() -> None:
    engine, repo, provider, _ = setup_engine()
    engine.process_webhook(subscription_event(), provider.signature)
    first = engine.process_webhook(invoice_event(), provider.signature)
    second = engine.process_webhook(invoice_event(), provider.signature)
    assert first.disposition == "PROCESSED"
    assert second.disposition == "DUPLICATE"
    assert repo.credit_balance("org-1") == 1000


def test_reused_provider_event_id_with_different_payload_fails_closed() -> None:
    engine, _, provider, _ = setup_engine()
    engine.process_webhook(subscription_event(), provider.signature)
    engine.process_webhook(invoice_event(), provider.signature)
    with pytest.raises(BillingError, match="EVENT_ID_COLLISION"):
        engine.process_webhook(
            invoice_event(event_id="evt-invoice-1", invoice_ref="different"),
            provider.signature,
        )


def test_delayed_old_plan_invoice_grants_old_plan_credits_not_current_plan() -> None:
    engine, repo, provider, _ = setup_engine()
    engine.process_webhook(subscription_event(), provider.signature)
    engine.process_webhook(
        subscription_event(event_id="evt-sub-v2", plan="pro-v2"),
        provider.signature,
    )
    subscription = repo.get_subscription("org-1")
    assert subscription is not None and subscription.plan_version_id == "pro-v2"
    engine.process_webhook(
        invoice_event(event_id="evt-old-invoice", invoice_ref="inv-v1", plan="pro-v1"),
        provider.signature,
    )
    assert repo.credit_balance("org-1") == 1000
    invoice = repo.list_invoices("org-1")[0]
    assert invoice.plan_version_id == "pro-v1"


def test_invalid_webhook_signature_and_state_fail_closed() -> None:
    engine, _, provider, _ = setup_engine()
    with pytest.raises(BillingError, match="SIGNATURE_INVALID"):
        engine.process_webhook(subscription_event(), "bad")
    with pytest.raises(BillingError, match="STATE_INVALID"):
        engine.process_webhook(
            subscription_event(state="provider_mystery_state"), provider.signature
        )


def test_credit_consumption_is_atomic_and_never_negative() -> None:
    engine, repo, _, actor = setup_engine()
    grant(repo, 10)

    def consume(index: int) -> str:
        try:
            engine.consume_usage(
                actor,
                project_id="project-1",
                pricing_policy_version=1,
                usage_key="image.standard",
                quantity=Decimal("1"),
                unit="image",
                usage_record_id=f"usage-{index}",
                idempotency_key=f"consume-{index}",
            )
            return "ok"
        except BillingError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, [1, 2]))
    assert sorted(results) == ["BILLING_INSUFFICIENT_CREDITS", "ok"]
    assert repo.credit_balance("org-1") == 0


def test_usage_idempotency_key_cannot_be_reused_for_another_usage_record() -> None:
    engine, repo, _, actor = setup_engine()
    grant(repo, 100)
    engine.consume_usage(
        actor,
        project_id=None,
        pricing_policy_version=1,
        usage_key="image.standard",
        quantity=Decimal("1"),
        unit="image",
        usage_record_id="usage-1",
        idempotency_key="consume-once",
    )
    with pytest.raises(BillingError, match="IDEMPOTENCY_KEY_REUSED"):
        engine.consume_usage(
            actor,
            project_id=None,
            pricing_policy_version=1,
            usage_key="image.standard",
            quantity=Decimal("1"),
            unit="image",
            usage_record_id="usage-2",
            idempotency_key="consume-once",
        )
    assert repo.credit_balance("org-1") == 90


def test_refund_appends_new_entry_without_mutating_consume() -> None:
    engine, repo, _, actor = setup_engine()
    grant(repo, 100)
    usage = engine.consume_usage(
        actor,
        project_id=None,
        pricing_policy_version=1,
        usage_key="image.standard",
        quantity=Decimal("1"),
        unit="image",
        usage_record_id="usage-1",
        idempotency_key="consume-1",
    )
    engine.refund_credits(
        actor,
        original_entry_id=usage.credit_entry_id,
        credits=10,
        idempotency_key="refund-1",
        reason="generation failed",
    )
    entries = repo.list_credit_entries("org-1")
    assert repo.credit_balance("org-1") == 100
    assert any(item.entry_type == "CONSUME" for item in entries)
    assert any(item.entry_type == "REFUND" for item in entries)


def test_concurrent_refunds_cannot_exceed_original_consume() -> None:
    engine, repo, _, actor = setup_engine()
    grant(repo, 100)
    usage = engine.consume_usage(
        actor,
        project_id=None,
        pricing_policy_version=1,
        usage_key="image.standard",
        quantity=Decimal("1"),
        unit="image",
        usage_record_id="usage-refund-race",
        idempotency_key="consume-refund-race",
    )

    def refund(index: int) -> str:
        try:
            engine.refund_credits(
                actor,
                original_entry_id=usage.credit_entry_id,
                credits=10,
                idempotency_key=f"refund-race-{index}",
                reason="failed",
            )
            return "ok"
        except BillingError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(refund, [1, 2]))
    assert sorted(results) == ["BILLING_REFUND_EXCEEDS_CONSUME", "ok"]
    assert repo.credit_balance("org-1") == 100


def test_cancelled_subscription_removes_paid_entitlements() -> None:
    engine, _, provider, actor = setup_engine()
    engine.process_webhook(subscription_event(), provider.signature)
    assert engine.entitlement(actor, "video_enabled") is True
    cancelled = engine.cancel_subscription(actor)
    assert cancelled.state == "CANCEL_AT_PERIOD_END"
    assert engine.entitlement(actor, "video_enabled") is True
    engine.process_webhook(
        json.dumps(
            {
                "id": "evt-cancelled",
                "type": "SUBSCRIPTION_CANCELLED",
                "organization_id": "org-1",
                "plan_version_id": "pro-v1",
                "subscription_ref": "mock_sub_1",
                "subscription_state": "CANCELLED",
            }
        ).encode(),
        provider.signature,
    )
    assert engine.entitlement(actor, "video_enabled") is None


def test_checkout_and_portal_are_hosted_and_no_payment_instrument_enters_domain() -> None:
    engine, _, _, actor = setup_engine()
    checkout = engine.create_checkout(actor, "pro-v2")
    portal = engine.create_portal(actor)
    assert checkout.url.startswith("https://checkout.mock.invalid/")
    assert portal.url.startswith("https://portal.mock.invalid/")


def test_provider_cost_and_customer_revenue_remain_separate() -> None:
    engine, _, provider, actor = setup_engine({"org-1": 12_000_000})
    engine.process_webhook(subscription_event(), provider.signature)
    engine.process_webhook(invoice_event(), provider.signature)
    report = engine.reconciliation(actor)
    assert report.provider_cost_microusd == 12_000_000
    assert report.paid_invoice_revenue_microusd == 49_000_000
    assert report.gross_margin_microusd == 37_000_000
