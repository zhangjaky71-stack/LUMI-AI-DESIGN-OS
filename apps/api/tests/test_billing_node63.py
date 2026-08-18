from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from lumi_api.billing import (
    BillingForbidden,
    BillingService,
    CreditWalletRecord,
    InvalidWebhook,
    MockPaymentProvider,
    PlanVersionRecord,
    SubscriptionRecord,
    SubscriptionState,
)

ROOT = Path(__file__).resolve().parents[3]


def _plan(*, version: int = 3) -> PlanVersionRecord:
    return PlanVersionRecord(
        id=uuid4(),
        plan_id=uuid4(),
        plan_key="studio",
        plan_name="Studio",
        version=version,
        currency="USD",
        monthly_price=Decimal("29.00"),
        included_credits=Decimal("1000"),
        postpaid_allowed=False,
        entitlements={"video.enabled": True, "generation.concurrent.max": 4},
        pricing_policy={"version": "credits-2026-08", "rates": {"image_generation": "4"}},
        effective_at=datetime.now(UTC),
    )


class FakeRepository:
    def __init__(self, *, state: SubscriptionState) -> None:
        self.organization_id = uuid4()
        self.plan = _plan()
        now = datetime.now(UTC)
        self.wallet = CreditWalletRecord(
            id=uuid4(),
            organization_id=self.organization_id,
            balance=Decimal("12"),
            allow_postpaid=False,
            updated_at=now,
        )
        self.subscription = SubscriptionRecord(
            id=uuid4(),
            organization_id=self.organization_id,
            billing_account_id=uuid4(),
            plan_version_id=self.plan.id,
            provider="mock",
            provider_subscription_ref="mock_sub_1",
            state=state,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
            cancel_at_period_end=state == SubscriptionState.CANCEL_AT_PERIOD_END,
            created_at=now,
            updated_at=now,
        )

    def ensure_wallet(self) -> CreditWalletRecord:
        return self.wallet

    def get_subscription(self) -> SubscriptionRecord:
        return self.subscription

    def get_subscription_plan(self, subscription: SubscriptionRecord) -> PlanVersionRecord:
        assert subscription.plan_version_id == self.plan.id
        return self.plan


def test_mock_provider_verifies_signature_and_rejects_card_data() -> None:
    provider = MockPaymentProvider("node63-secret")
    organization_id = uuid4()
    payload = {
        "id": "evt_1",
        "type": "subscription.updated",
        "organization_id": str(organization_id),
        "occurred_at": datetime.now(UTC).isoformat(),
        "subscription_ref": "mock_sub_1",
        "plan_key": "studio",
        "plan_version": 3,
        "subscription_state": "ACTIVE",
        "metadata": {"customer_ref": "mock_customer_1"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    event = provider.verify_webhook(body=body, signature=provider.sign(body))
    assert event.organization_id == organization_id
    assert event.subscription_state == SubscriptionState.ACTIVE

    with pytest.raises(InvalidWebhook, match="SIGNATURE_INVALID"):
        provider.verify_webhook(body=body, signature="bad")

    bad_body = json.dumps({**payload, "cvc": "123"}).encode()
    with pytest.raises(InvalidWebhook, match="CARD_DATA_FORBIDDEN"):
        provider.verify_webhook(body=bad_body, signature=provider.sign(bad_body))


def test_entitlements_are_snapshot_driven_and_cancelled_state_revokes() -> None:
    active_repo = FakeRepository(state=SubscriptionState.ACTIVE)
    active = BillingService(active_repo, MockPaymentProvider("secret"))  # type: ignore[arg-type]
    snapshot = active.entitlements(permissions=("billing.read",))
    assert snapshot.entitlements["video.enabled"] is True
    assert snapshot.plan_version_id == active_repo.plan.id

    cancelled_repo = FakeRepository(state=SubscriptionState.CANCELLED)
    cancelled = BillingService(cancelled_repo, MockPaymentProvider("secret"))  # type: ignore[arg-type]
    cancelled_snapshot = cancelled.entitlements(permissions=("billing.read",))
    assert cancelled_snapshot.entitlements == {}
    assert cancelled_snapshot.can_consume_paid_features is False


def test_pricing_policy_is_versioned_and_not_provider_cost() -> None:
    repo = FakeRepository(state=SubscriptionState.ACTIVE)
    service = BillingService(repo, MockPaymentProvider("secret"))  # type: ignore[arg-type]
    amount, policy_version = service.price_usage(
        plan=repo.plan,
        metric="image_generation",
        quantity=Decimal("2"),
    )
    assert amount == Decimal("8")
    assert policy_version == "credits-2026-08"


def test_billing_read_permission_is_enforced() -> None:
    repo = FakeRepository(state=SubscriptionState.ACTIVE)
    service = BillingService(repo, MockPaymentProvider("secret"))  # type: ignore[arg-type]
    with pytest.raises(BillingForbidden, match="PERMISSION_DENIED"):
        service.entitlements(permissions=("project.read",))


def test_node63_repository_and_migration_encode_no_overdraw_and_idempotency() -> None:
    repository = (ROOT / "apps/api/src/lumi_api/billing/repository.py").read_text()
    migration = (
        ROOT / "apps/api/migrations/versions/20260818_0023_sql/up.sql"
    ).read_text()
    reconciliation = (ROOT / "apps/api/src/lumi_api/billing/reconciliation.py").read_text()
    provider = (ROOT / "apps/api/src/lumi_api/billing/provider.py").read_text()

    assert "FOR UPDATE" in repository
    assert "BILLING_INSUFFICIENT_CREDITS" in repository
    assert "uq_billing_provider_event" in migration
    assert "uq_billing_credit_operation" in migration
    assert "trg_billing_credit_ledger_immutable" in migration
    assert "trg_billing_plan_version_material_immutable" in migration
    assert "provider_event_id" in repository and "body_sha256" in repository
    assert "UPDATE cost_ledger" not in repository
    assert "INSERT INTO cost_ledger" not in repository
    assert "UPDATE cost_ledger" not in reconciliation
    assert "INSERT INTO cost_ledger" not in reconciliation
    assert "card_number" in provider and "cvc" in provider


def test_webhook_router_is_signature_boundary_not_user_auth_boundary() -> None:
    app_source = (ROOT / "apps/api/src/lumi_api/api/v1/app.py").read_text()
    routes = (ROOT / "apps/api/src/lumi_api/api/v1/billing_routes.py").read_text()
    assert "app.include_router(billing_webhook_router)" in app_source
    assert "app.include_router(billing_router, dependencies=[Depends(enforce_api_auth)])" in app_source
    assert 'Header(alias="X-Lumi-Mock-Signature")' in routes
    assert "card_number" not in routes.casefold()
