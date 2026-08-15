from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lumi_api.billing_router import create_billing_router
from lumi_project_core.billing import (
    BillingActor,
    BillingEngine,
    InMemoryBillingRepository,
    MockPaymentProvider,
    PlanVersion,
    StaticProviderCostPort,
)


def make_client() -> tuple[TestClient, BillingEngine, MockPaymentProvider]:
    repo = InMemoryBillingRepository()
    provider = MockPaymentProvider()
    engine = BillingEngine(
        repository=repo,
        payment_provider=provider,
        provider_costs=StaticProviderCostPort(),
    )
    admin = BillingActor(
        "owner",
        "org-1",
        frozenset({"billing.read", "billing.manage"}),
        "owner@example.com",
    )
    engine.publish_plan_version(
        admin,
        PlanVersion(
            "pro",
            "pro-v1",
            1,
            "Pro",
            "USD",
            49_000_000,
            "MONTH",
            1000,
            {"video_enabled": True, "team_seats": 5},
        ),
    )

    async def resolve_actor(request: Request) -> BillingActor:
        mode = request.headers.get("x-test-role", "owner")
        permissions = (
            {"billing.read", "billing.manage"} if mode == "owner" else {"billing.read"}
        )
        return BillingActor(mode, "org-1", frozenset(permissions), f"{mode}@example.com")

    app = FastAPI()
    app.include_router(create_billing_router(engine=engine, resolve_actor=resolve_actor))
    return TestClient(app), engine, provider


def subscription_payload() -> dict[str, object]:
    return {
        "id": "evt-sub-1",
        "type": "SUBSCRIPTION_CREATED",
        "organization_id": "org-1",
        "plan_version_id": "pro-v1",
        "subscription_ref": "mock_sub_1",
        "subscription_state": "ACTIVE",
    }


def test_billing_summary_and_manage_affordance() -> None:
    client, _, _ = make_client()
    owner = client.get("/billing")
    viewer = client.get("/billing", headers={"x-test-role": "viewer"})
    assert owner.status_code == 200 and owner.json()["can_manage"] is True
    assert viewer.status_code == 200 and viewer.json()["can_manage"] is False


def test_checkout_requires_billing_manage_and_returns_hosted_url() -> None:
    client, _, _ = make_client()
    denied = client.post(
        "/billing/checkout",
        json={"plan_version_id": "pro-v1"},
        headers={"x-test-role": "viewer"},
    )
    assert denied.status_code == 403
    allowed = client.post("/billing/checkout", json={"plan_version_id": "pro-v1"})
    assert allowed.status_code == 200
    assert allowed.json()["url"].startswith("https://checkout.mock.invalid/")


def test_webhook_signature_and_duplicate_idempotency() -> None:
    client, _, provider = make_client()
    event = json.dumps(subscription_payload())
    invalid = client.post(
        "/billing/webhooks/mock",
        content=event,
        headers={"X-Lumi-Payment-Signature": "bad"},
    )
    assert invalid.status_code == 401
    headers = {"X-Lumi-Payment-Signature": provider.signature}
    first = client.post("/billing/webhooks/mock", content=event, headers=headers)
    second = client.post("/billing/webhooks/mock", content=event, headers=headers)
    assert first.json()["disposition"] == "PROCESSED"
    assert second.json()["disposition"] == "DUPLICATE"


def test_invoice_paid_grants_exact_plan_credits_once() -> None:
    client, _, provider = make_client()
    headers = {"X-Lumi-Payment-Signature": provider.signature}
    client.post(
        "/billing/webhooks/mock",
        content=json.dumps(subscription_payload()),
        headers=headers,
    )
    invoice = json.dumps(
        {
            "id": "evt-inv-1",
            "type": "INVOICE_PAID",
            "organization_id": "org-1",
            "plan_version_id": "pro-v1",
            "invoice_ref": "inv-1",
            "amount_due_microusd": 49_000_000,
            "currency": "USD",
        }
    )
    client.post("/billing/webhooks/mock", content=invoice, headers=headers)
    client.post("/billing/webhooks/mock", content=invoice, headers=headers)
    summary = client.get("/billing").json()
    assert summary["credit_balance"] == 1000
    assert summary["invoices"][0]["plan_version_id"] == "pro-v1"
