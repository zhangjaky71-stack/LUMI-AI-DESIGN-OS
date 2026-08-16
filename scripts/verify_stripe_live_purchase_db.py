from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


REQUIRED_ENV = (
    "DATABASE_URL",
    "LUMI_ACCEPTANCE_ORGANIZATION_ID",
    "LUMI_ACCEPTANCE_PLAN_VERSION_ID",
    "LUMI_ACCEPTANCE_SUBSCRIPTION_REF",
    "LUMI_ACCEPTANCE_INVOICE_REF",
    "LUMI_ACCEPTANCE_SUBSCRIPTION_EVENT_ID",
    "LUMI_ACCEPTANCE_INVOICE_EVENT_ID",
)


def _required_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(
            "missing Stripe live purchase evidence input(s): " + ", ".join(missing)
        )
    try:
        UUID(values["LUMI_ACCEPTANCE_ORGANIZATION_ID"])
    except ValueError as error:
        raise SystemExit("LUMI_ACCEPTANCE_ORGANIZATION_ID must be a UUID") from error
    return values


async def main() -> None:
    values = _required_environment()
    database_url = values["DATABASE_URL"]
    organization_id = values["LUMI_ACCEPTANCE_ORGANIZATION_ID"]
    plan_version_id = values["LUMI_ACCEPTANCE_PLAN_VERSION_ID"]
    subscription_ref = values["LUMI_ACCEPTANCE_SUBSCRIPTION_REF"]
    invoice_ref = values["LUMI_ACCEPTANCE_INVOICE_REF"]
    subscription_event_id = values["LUMI_ACCEPTANCE_SUBSCRIPTION_EVENT_ID"]
    invoice_event_id = values["LUMI_ACCEPTANCE_INVOICE_EVENT_ID"]

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text("SELECT set_config('app.current_organization_id', :org, true)"),
                    {"org": organization_id},
                )

                plan = (
                    await connection.execute(
                        text("""
                        SELECT plan_version_id, price_microusd, currency,
                               monthly_credit_grant, status
                        FROM billing_plan_versions
                        WHERE plan_version_id=:plan
                        """),
                        {"plan": plan_version_id},
                    )
                ).mappings().one_or_none()
                if plan is None:
                    raise SystemExit("configured LUMI plan version was not found")
                if plan["status"] != "ACTIVE":
                    raise SystemExit("acceptance plan version is not ACTIVE")
                if plan["currency"] != "USD":
                    raise SystemExit("acceptance plan currency is not USD")

                account = (
                    await connection.execute(
                        text("""
                        SELECT payment_provider, payment_customer_ref
                        FROM billing_accounts
                        WHERE organization_id=CAST(:org AS uuid)
                        """),
                        {"org": organization_id},
                    )
                ).mappings().one_or_none()
                if account is None or account["payment_provider"] != "STRIPE":
                    raise SystemExit("STRIPE billing account was not found")

                subscription = (
                    await connection.execute(
                        text("""
                        SELECT plan_version_id, payment_provider,
                               provider_subscription_ref, state,
                               cancel_at_period_end
                        FROM billing_subscriptions
                        WHERE organization_id=CAST(:org AS uuid)
                        """),
                        {"org": organization_id},
                    )
                ).mappings().one_or_none()
                if subscription is None:
                    raise SystemExit("billing subscription was not found")
                if subscription["payment_provider"] != "STRIPE":
                    raise SystemExit("billing subscription provider is not STRIPE")
                if subscription["provider_subscription_ref"] != subscription_ref:
                    raise SystemExit("subscription reference does not match live evidence")
                if subscription["plan_version_id"] != plan_version_id:
                    raise SystemExit("subscription plan version does not match acceptance plan")
                if subscription["state"] != "ACTIVE":
                    raise SystemExit("subscription is not ACTIVE after live purchase")

                invoice = (
                    await connection.execute(
                        text("""
                        SELECT plan_version_id, status, amount_due_microusd, currency
                        FROM billing_invoices
                        WHERE organization_id=CAST(:org AS uuid)
                          AND provider='STRIPE'
                          AND provider_invoice_ref=:invoice
                        """),
                        {"org": organization_id, "invoice": invoice_ref},
                    )
                ).mappings().one_or_none()
                if invoice is None:
                    raise SystemExit("live invoice reference was not found")
                if invoice["plan_version_id"] != plan_version_id:
                    raise SystemExit("invoice plan version does not match acceptance plan")
                if invoice["status"] != "PAID":
                    raise SystemExit("live invoice is not PAID")
                if invoice["currency"] != "USD":
                    raise SystemExit("live invoice currency is not USD")
                if invoice["amount_due_microusd"] != plan["price_microusd"]:
                    raise SystemExit("live invoice amount does not match immutable plan price")

                event_rows = (
                    await connection.execute(
                        text("""
                        SELECT provider_event_id, event_type, count(*) AS row_count
                        FROM billing_payment_events
                        WHERE organization_id=CAST(:org AS uuid)
                          AND provider='STRIPE'
                          AND provider_event_id IN (:subscription_event, :invoice_event)
                        GROUP BY provider_event_id, event_type
                        """),
                        {
                            "org": organization_id,
                            "subscription_event": subscription_event_id,
                            "invoice_event": invoice_event_id,
                        },
                    )
                ).mappings().all()
                events = {
                    row["provider_event_id"]: (row["event_type"], int(row["row_count"]))
                    for row in event_rows
                }
                if events.get(subscription_event_id) != ("SUBSCRIPTION_CREATED", 1):
                    raise SystemExit(
                        "exact subscription-created Stripe event is not present once"
                    )
                if events.get(invoice_event_id) != ("INVOICE_PAID", 1):
                    raise SystemExit("exact invoice-paid Stripe event is not present once")

                credit = (
                    await connection.execute(
                        text("""
                        SELECT count(*) AS grant_count,
                               COALESCE(sum(delta_credits), 0) AS granted_credits
                        FROM billing_credit_ledger
                        WHERE organization_id=CAST(:org AS uuid)
                          AND entry_type='GRANT'
                          AND source_type='INVOICE'
                          AND source_id=:invoice
                          AND idempotency_key=:idempotency_key
                        """),
                        {
                            "org": organization_id,
                            "invoice": invoice_ref,
                            "idempotency_key": (
                                f"invoice:STRIPE:{invoice_ref}:"
                                f"{plan_version_id}:credit-grant"
                            ),
                        },
                    )
                ).mappings().one()
                if int(credit["grant_count"]) != 1:
                    raise SystemExit("live invoice credit grant count is not exactly one")
                if int(credit["granted_credits"]) != int(plan["monthly_credit_grant"]):
                    raise SystemExit("live invoice credit grant amount does not match plan")

                total_credit_balance = await connection.scalar(
                    text("""
                    SELECT COALESCE(sum(delta_credits), 0)
                    FROM billing_credit_ledger
                    WHERE organization_id=CAST(:org AS uuid)
                    """),
                    {"org": organization_id},
                )
    finally:
        await engine.dispose()

    print(
        json.dumps(
            {
                "status": "STRIPE_LIVE_PURCHASE_DB_PASS",
                "organization_id": organization_id,
                "plan_version_id": plan_version_id,
                "stripe_customer_id": account["payment_customer_ref"],
                "stripe_subscription_id": subscription_ref,
                "stripe_invoice_id": invoice_ref,
                "stripe_subscription_event_id": subscription_event_id,
                "stripe_invoice_event_id": invoice_event_id,
                "subscription_state": subscription["state"],
                "invoice_state": invoice["status"],
                "currency": invoice["currency"],
                "amount_due_microusd": int(invoice["amount_due_microusd"]),
                "credit_grant_count": int(credit["grant_count"]),
                "granted_credits": int(credit["granted_credits"]),
                "credit_balance": int(total_credit_balance or 0),
                "event_rows_unique": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
