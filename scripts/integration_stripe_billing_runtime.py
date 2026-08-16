from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from threading import Lock
import time
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lumi_api.billing_runtime import AsyncStripeBillingRuntime
from lumi_project_core.billing import BillingActor, BillingError, PlanVersion
from lumi_project_core.stripe_provider import StripePaymentProvider, StripeProviderConfig


WEBHOOK_SECRET = "whsec_local_acceptance"


class FakeStripeTransport:
    """Thread-safe deterministic Stripe transport used only by PostgreSQL acceptance."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._customers: dict[str, str] = {}
        self._customer_organizations: dict[str, str] = {}
        self.customer_posts = 0
        self.checkout_posts = 0

    def __call__(
        self,
        method: str,
        path: str,
        fields: list[tuple[str, str]] | None,
        _secret_key: str,
        idempotency_key: str | None,
    ) -> dict[str, object]:
        values = dict(fields or [])
        if method == "POST" and path == "/customers":
            organization_id = values["metadata[organization_id]"]
            if idempotency_key != f"lumi-customer:{organization_id}":
                raise AssertionError("stable Stripe customer idempotency key missing")
            with self._lock:
                self.customer_posts += 1
                customer = self._customers.get(idempotency_key)
                if customer is None:
                    customer = f"cus_accept_{len(self._customers) + 1}"
                    self._customers[idempotency_key] = customer
                    self._customer_organizations[customer] = organization_id
            return {"id": customer}

        if method == "GET" and path.startswith("/customers/"):
            customer = path.rsplit("/", 1)[-1]
            organization_id = self._customer_organizations[customer]
            return {"id": customer, "metadata": {"organization_id": organization_id}}

        if method == "POST" and path == "/checkout/sessions":
            with self._lock:
                self.checkout_posts += 1
                checkout_number = self.checkout_posts
            return {
                "id": f"cs_accept_{checkout_number}",
                "url": f"https://checkout.stripe.com/c/pay/cs_accept_{checkout_number}",
            }

        raise AssertionError(f"unexpected fake Stripe call: {method} {path}")


def _signature(raw: bytes, timestamp: int) -> str:
    digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        str(timestamp).encode("ascii") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _event_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


async def _insert_organization(database_url: str, organization_id: str, slug: str) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                INSERT INTO organizations(
                  id, name, slug, status, plan, settings_json,
                  created_at, updated_at, version
                ) VALUES (
                  CAST(:id AS uuid), :name, :slug, 'active', 'free',
                  '{}'::jsonb, now(), now(), 1
                )
                """),
                {"id": organization_id, "name": "Stripe Acceptance", "slug": slug},
            )
    finally:
        await engine.dispose()


async def _assert_immutable_controls(
    migration_database_url: str,
    organization_id: str,
    plan_version_id: str,
) -> None:
    engine = create_async_engine(migration_database_url, pool_pre_ping=True)
    try:
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE billing_plan_versions SET name='mutated' "
                        "WHERE plan_version_id=:plan"
                    ),
                    {"plan": plan_version_id},
                )
        except DBAPIError as error:
            if "BILLING_PLAN_VERSION_IMMUTABLE" not in str(error):
                raise
        else:
            raise AssertionError("billing plan version mutation unexpectedly succeeded")

        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("SELECT set_config('app.current_organization_id', :org, true)"),
                    {"org": organization_id},
                )
                await connection.execute(
                    text(
                        "UPDATE billing_credit_ledger SET delta_credits=delta_credits + 1 "
                        "WHERE organization_id=CAST(:org AS uuid)"
                    ),
                    {"org": organization_id},
                )
        except DBAPIError as error:
            if "BILLING_CREDIT_LEDGER_IMMUTABLE" not in str(error):
                raise
        else:
            raise AssertionError("billing credit ledger mutation unexpectedly succeeded")
    finally:
        await engine.dispose()


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    migration_database_url = os.environ["MIGRATION_DATABASE_URL"]
    organization_id = str(uuid4())
    slug = f"stripe-accept-{organization_id.split('-')[0]}"
    plan_id = f"accept-{organization_id.split('-')[0]}"
    plan_version_id = f"{plan_id}-v1"

    await _insert_organization(migration_database_url, organization_id, slug)

    plan = PlanVersion(
        plan_id=plan_id,
        plan_version_id=plan_version_id,
        version=1,
        name="Stripe Acceptance Pro",
        currency="USD",
        price_microusd=2_000_000,
        billing_interval="MONTH",
        monthly_credit_grant=500,
        entitlements={"generations": 100, "billing_acceptance": True},
    )
    transport = FakeStripeTransport()
    provider = StripePaymentProvider(
        StripeProviderConfig(
            secret_key="sk_test_local_acceptance",
            webhook_secret=WEBHOOK_SECRET,
            price_ids_by_plan_version={plan_version_id: "price_acceptance"},
            checkout_success_url="https://acceptance.example.test/billing/success",
            checkout_cancel_url="https://acceptance.example.test/billing",
            portal_return_url="https://acceptance.example.test/billing",
            expected_livemode=False,
        ),
        transport=transport,
    )

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    runtime = AsyncStripeBillingRuntime(
        session_factory=sessions,
        payment_provider=provider,
        plan_catalog=(plan,),
    )
    actor = BillingActor(
        actor_id=str(uuid4()),
        organization_id=organization_id,
        permissions=frozenset({"billing.read", "billing.manage"}),
        billing_email="billing-acceptance@example.test",
    )

    try:
        await runtime.initialize_catalog()

        first, second = await asyncio.gather(
            runtime.create_checkout(actor, plan_version_id),
            runtime.create_checkout(actor, plan_version_id),
        )
        assert first.session_ref != second.session_ref
        assert transport.checkout_posts == 2
        assert transport.customer_posts == 1, (
            "concurrent first checkout created more than one Stripe customer"
        )

        timestamp = int(time.time())
        subscription_event_id = f"evt_sub_{organization_id}"
        subscription_raw = _event_bytes(
            {
                "id": subscription_event_id,
                "type": "customer.subscription.created",
                "livemode": False,
                "data": {
                    "object": {
                        "id": f"sub_{organization_id}",
                        "customer": "cus_accept_1",
                        "status": "active",
                        "cancel_at_period_end": False,
                        "current_period_start": timestamp - 30,
                        "current_period_end": timestamp + 3600,
                        "metadata": {
                            "organization_id": organization_id,
                            "plan_version_id": plan_version_id,
                        },
                    }
                },
            }
        )
        subscription_result = await runtime.process_webhook(
            subscription_raw, _signature(subscription_raw, timestamp)
        )
        assert subscription_result.disposition == "PROCESSED"

        invoice_event_id = f"evt_invoice_{organization_id}"
        invoice_ref = f"in_{organization_id}"
        invoice_raw = _event_bytes(
            {
                "id": invoice_event_id,
                "type": "invoice.paid",
                "livemode": False,
                "data": {
                    "object": {
                        "id": invoice_ref,
                        "customer": "cus_accept_1",
                        "amount_due": 200,
                        "currency": "usd",
                        "hosted_invoice_url": "https://invoice.stripe.com/i/acceptance",
                        "parent": {
                            "subscription_details": {
                                "subscription": f"sub_{organization_id}",
                                "metadata": {
                                    "organization_id": organization_id,
                                    "plan_version_id": plan_version_id,
                                },
                            }
                        },
                    }
                },
            }
        )
        invoice_result = await runtime.process_webhook(
            invoice_raw, _signature(invoice_raw, timestamp)
        )
        assert invoice_result.disposition == "PROCESSED"
        duplicate_result = await runtime.process_webhook(
            invoice_raw, _signature(invoice_raw, timestamp)
        )
        assert duplicate_result.disposition == "DUPLICATE"

        collision_payload = json.loads(invoice_raw)
        collision_payload["data"]["object"]["amount_due"] = 201
        collision_raw = _event_bytes(collision_payload)
        try:
            await runtime.process_webhook(
                collision_raw, _signature(collision_raw, timestamp)
            )
        except BillingError as error:
            assert error.code == "BILLING_WEBHOOK_EVENT_ID_COLLISION"
        else:
            raise AssertionError("provider event ID collision did not fail closed")

        summary = await runtime.summary(actor)
        assert summary.subscription is not None
        assert summary.subscription.state == "ACTIVE"
        assert summary.current_plan is not None
        assert summary.current_plan.plan_version_id == plan_version_id
        assert summary.credit_balance == 500
        assert len(summary.invoices) == 1
        assert summary.invoices[0].provider_invoice_ref == invoice_ref
        assert summary.entitlements["billing_acceptance"] is True

        other_organization_id = str(uuid4())
        async with sessions() as session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.current_organization_id', :org, true)"),
                    {"org": other_organization_id},
                )
                visible_events = await session.scalar(
                    text(
                        "SELECT count(*) FROM billing_payment_events "
                        "WHERE provider='STRIPE' AND provider_event_id=:event_id"
                    ),
                    {"event_id": invoice_event_id},
                )
                assert int(visible_events or 0) == 0

                privileges = (
                    await session.execute(
                        text("""
                        SELECT
                          has_table_privilege(current_user, 'billing_credit_ledger', 'INSERT'),
                          has_table_privilege(current_user, 'billing_credit_ledger', 'UPDATE'),
                          has_table_privilege(current_user, 'billing_payment_events', 'INSERT'),
                          has_table_privilege(current_user, 'billing_payment_events', 'DELETE'),
                          has_table_privilege(current_user, 'billing_invoices', 'UPDATE')
                        """)
                    )
                ).one()
                assert privileges == (True, False, True, False, True)

        await _assert_immutable_controls(
            migration_database_url,
            organization_id,
            plan_version_id,
        )
    finally:
        await engine.dispose()

    print(
        json.dumps(
            {
                "status": "STRIPE_BILLING_POSTGRES_ACCEPTANCE_PASS",
                "organization_id": organization_id,
                "plan_version_id": plan_version_id,
                "stripe_customer_posts": transport.customer_posts,
                "checkout_posts": transport.checkout_posts,
                "webhook_replay": "DUPLICATE",
                "credit_balance": 500,
                "rls_isolation": "PASS",
                "least_privilege": "PASS",
                "immutable_ledgers": "PASS",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
