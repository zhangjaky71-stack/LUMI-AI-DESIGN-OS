from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4

from anyio import to_thread
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_project_core.billing import (
    BillingAccount,
    BillingActor,
    BillingError,
    BillingSummary,
    CreditLedgerEntry,
    HostedSession,
    InvoiceRef,
    NormalizedPaymentEvent,
    PaymentProcessResult,
    PlanVersion,
    Subscription,
)
from lumi_project_core.stripe_provider import StripePaymentProvider, StripeProviderConfig


class AsyncStripeBillingRuntime:
    """Production Stripe billing service backed by PostgreSQL."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        payment_provider: StripePaymentProvider,
        plan_catalog: tuple[PlanVersion, ...],
    ) -> None:
        self._sessions = session_factory
        self._provider = payment_provider
        self._catalog = plan_catalog

    @property
    def payment_provider_name(self) -> str:
        return self._provider.name

    async def initialize_catalog(self) -> None:
        """Validate Stripe Prices, then insert immutable plan versions or reject drift."""
        for plan in self._catalog:
            await to_thread.run_sync(self._provider.validate_plan_price, plan)

        async with self._sessions() as session:
            async with session.begin():
                for plan in self._catalog:
                    row = (
                        await session.execute(
                            text("SELECT * FROM billing_plan_versions WHERE plan_version_id=:id"),
                            {"id": plan.plan_version_id},
                        )
                    ).mappings().first()
                    if row is None:
                        await session.execute(
                            text("""
                            INSERT INTO billing_plan_versions(
                              plan_version_id, plan_id, version, name, currency,
                              price_microusd, billing_interval, monthly_credit_grant,
                              entitlements, status
                            ) VALUES (
                              :plan_version_id, :plan_id, :version, :name, :currency,
                              :price_microusd, :billing_interval, :monthly_credit_grant,
                              CAST(:entitlements AS jsonb), :status
                            )
                            """),
                            {
                                **_plan_params(plan),
                                "entitlements": json.dumps(plan.entitlements, separators=(",", ":")),
                            },
                        )
                        continue
                    if _plan_from_row(row) != plan:
                        raise RuntimeError(
                            f"configured plan drifted from immutable database row: {plan.plan_version_id}"
                        )

    async def summary(self, actor: BillingActor) -> BillingSummary:
        _require(actor, "billing.read")
        async with self._sessions() as session:
            async with session.begin():
                await _set_tenant(session, actor.organization_id)
                subscription = await _get_subscription(session, actor.organization_id)
                current_plan = (
                    await _get_plan(session, subscription.plan_version_id)
                    if subscription is not None
                    else None
                )
                plans = await _list_active_plans(session)
                credits = await _list_credits(session, actor.organization_id, limit=20)
                invoices = await _list_invoices(session, actor.organization_id, limit=20)
                balance = await _credit_balance(session, actor.organization_id)
        return BillingSummary(
            organization_id=actor.organization_id,
            current_plan=current_plan,
            subscription=subscription,
            plans=plans,
            credit_balance=balance,
            credit_entries=credits,
            invoices=invoices,
            entitlements=(
                dict(current_plan.entitlements)
                if subscription is not None
                and current_plan is not None
                and subscription.state in {"TRIALING", "ACTIVE", "CANCEL_AT_PERIOD_END"}
                else {}
            ),
            can_manage="billing.manage" in actor.permissions,
            payment_provider=self._provider.name,
            provider_cost_reconciliation_available=True,
        )

    async def create_checkout(self, actor: BillingActor, plan_version_id: str) -> HostedSession:
        _require(actor, "billing.manage")
        async with self._sessions() as session:
            async with session.begin():
                await _set_tenant(session, actor.organization_id)
                plan = await _get_plan(session, plan_version_id)
                if plan is None or plan.status != "ACTIVE":
                    raise BillingError("BILLING_PLAN_VERSION_NOT_AVAILABLE", 404)
                account = await _get_account(session, actor.organization_id)
                if account is None:
                    await session.execute(
                        text(
                            "SELECT pg_advisory_xact_lock("
                            "hashtextextended('billing-customer:' || :org, 0))"
                        ),
                        {"org": actor.organization_id},
                    )
                    account = await _get_account(session, actor.organization_id)
                    if account is None:
                        customer_ref = await to_thread.run_sync(
                            self._provider.create_customer,
                            actor.organization_id,
                            actor.billing_email,
                        )
                        await session.execute(
                            text("""
                            INSERT INTO billing_accounts(
                              organization_id, payment_provider, payment_customer_ref
                            ) VALUES (:org, :provider, :customer)
                            ON CONFLICT (organization_id) DO NOTHING
                            """),
                            {
                                "org": actor.organization_id,
                                "provider": self._provider.name,
                                "customer": customer_ref,
                            },
                        )
                        account = await _get_account(session, actor.organization_id)
        if account is None:
            raise BillingError("BILLING_ACCOUNT_PERSIST_FAILED", 503)
        if account.payment_provider != self._provider.name:
            raise BillingError("BILLING_PAYMENT_PROVIDER_MISMATCH", 409)
        return await to_thread.run_sync(
            self._provider.create_checkout, account.payment_customer_ref, plan
        )

    async def create_portal(self, actor: BillingActor) -> HostedSession:
        _require(actor, "billing.manage")
        async with self._sessions() as session:
            async with session.begin():
                await _set_tenant(session, actor.organization_id)
                account = await _get_account(session, actor.organization_id)
        if account is None:
            raise BillingError("BILLING_PAYMENT_CUSTOMER_NOT_FOUND", 404)
        if account.payment_provider != self._provider.name:
            raise BillingError("BILLING_PAYMENT_PROVIDER_MISMATCH", 409)
        return await to_thread.run_sync(
            self._provider.create_portal_session, account.payment_customer_ref
        )

    async def cancel_subscription(self, actor: BillingActor) -> Subscription:
        _require(actor, "billing.manage")
        async with self._sessions() as session:
            async with session.begin():
                await _set_tenant(session, actor.organization_id)
                current = await _get_subscription(session, actor.organization_id)
        if current is None:
            raise BillingError("BILLING_SUBSCRIPTION_NOT_FOUND", 404)
        provider_state = await to_thread.run_sync(
            self._provider.cancel_subscription, current.provider_subscription_ref
        )
        async with self._sessions() as session:
            async with session.begin():
                await _set_tenant(session, actor.organization_id)
                await session.execute(
                    text("""
                    UPDATE billing_subscriptions SET
                      state=:state,
                      cancel_at_period_end=:cancel,
                      current_period_start=:period_start,
                      current_period_end=:period_end,
                      updated_at=now()
                    WHERE organization_id=:org AND provider_subscription_ref=:provider_ref
                    """),
                    {
                        "org": actor.organization_id,
                        "provider_ref": current.provider_subscription_ref,
                        "state": provider_state.state,
                        "cancel": provider_state.cancel_at_period_end,
                        "period_start": provider_state.current_period_start,
                        "period_end": provider_state.current_period_end,
                    },
                )
                updated = await _get_subscription(session, actor.organization_id)
        if updated is None:
            raise BillingError("BILLING_SUBSCRIPTION_PERSIST_FAILED", 503)
        return updated

    async def process_webhook(self, raw_body: bytes, signature: str) -> PaymentProcessResult:
        normalized, payload_hash = await to_thread.run_sync(
            self._provider.verify_webhook, raw_body, signature
        )
        async with self._sessions() as session:
            async with session.begin():
                await _set_tenant(session, normalized.organization_id)
                claimed = (
                    await session.execute(
                        text("""
                        INSERT INTO billing_payment_events(
                          provider, provider_event_id, organization_id,
                          event_type, payload_hash, received_at
                        ) VALUES (
                          :provider, :event_id, :org, :event_type, :payload_hash, now()
                        )
                        ON CONFLICT (provider, provider_event_id) DO NOTHING
                        RETURNING provider_event_id
                        """),
                        {
                            "provider": normalized.provider,
                            "event_id": normalized.provider_event_id,
                            "org": normalized.organization_id,
                            "event_type": normalized.event_type,
                            "payload_hash": payload_hash,
                        },
                    )
                ).scalar_one_or_none()
                if claimed is None:
                    prior = (
                        await session.execute(
                            text("""
                            SELECT payload_hash, organization_id
                            FROM billing_payment_events
                            WHERE provider=:provider AND provider_event_id=:event_id
                            """),
                            {
                                "provider": normalized.provider,
                                "event_id": normalized.provider_event_id,
                            },
                        )
                    ).mappings().first()
                    if prior is None:
                        raise BillingError("BILLING_WEBHOOK_EVENT_CLAIM_FAILED", 503)
                    if prior["payload_hash"] != payload_hash:
                        raise BillingError("BILLING_WEBHOOK_EVENT_ID_COLLISION", 409)
                    return PaymentProcessResult(
                        provider_event_id=normalized.provider_event_id,
                        disposition="DUPLICATE",
                    )
                await self._apply_event(session, normalized)
        return PaymentProcessResult(
            provider_event_id=normalized.provider_event_id,
            disposition="PROCESSED",
        )

    async def _apply_event(
        self, session: AsyncSession, event: NormalizedPaymentEvent
    ) -> None:
        if event.event_type in {
            "SUBSCRIPTION_CREATED",
            "SUBSCRIPTION_UPDATED",
            "SUBSCRIPTION_CANCELLED",
        }:
            if not event.subscription_ref or not event.plan_version_id or not event.subscription_state:
                raise BillingError("BILLING_WEBHOOK_SUBSCRIPTION_INCOMPLETE")
            if await _get_plan(session, event.plan_version_id) is None:
                raise BillingError("BILLING_WEBHOOK_PLAN_VERSION_UNKNOWN", 409)
            await session.execute(
                text("""
                INSERT INTO billing_subscriptions(
                  subscription_id, organization_id, plan_version_id, payment_provider,
                  provider_subscription_ref, state, current_period_start, current_period_end,
                  cancel_at_period_end, updated_at
                ) VALUES (
                  :subscription_id, :org, :plan, :provider, :provider_ref,
                  :state, :period_start, :period_end, :cancel, now()
                )
                ON CONFLICT (organization_id) DO UPDATE SET
                  plan_version_id=EXCLUDED.plan_version_id,
                  payment_provider=EXCLUDED.payment_provider,
                  provider_subscription_ref=EXCLUDED.provider_subscription_ref,
                  state=EXCLUDED.state,
                  current_period_start=EXCLUDED.current_period_start,
                  current_period_end=EXCLUDED.current_period_end,
                  cancel_at_period_end=EXCLUDED.cancel_at_period_end,
                  updated_at=now()
                """),
                {
                    "subscription_id": f"sub-{event.organization_id}",
                    "org": event.organization_id,
                    "plan": event.plan_version_id,
                    "provider": event.provider,
                    "provider_ref": event.subscription_ref,
                    "state": event.subscription_state,
                    "period_start": event.period_start,
                    "period_end": event.period_end,
                    "cancel": event.subscription_state == "CANCEL_AT_PERIOD_END",
                },
            )
            return

        if (
            not event.invoice_ref
            or not event.plan_version_id
            or event.amount_due_microusd is None
            or not event.currency
        ):
            raise BillingError("BILLING_WEBHOOK_INVOICE_INCOMPLETE")
        plan = await _get_plan(session, event.plan_version_id)
        if plan is None:
            raise BillingError("BILLING_WEBHOOK_PLAN_VERSION_UNKNOWN", 409)
        status = "PAID" if event.event_type == "INVOICE_PAID" else "FAILED"
        prior = (
            await session.execute(
                text("""
                SELECT plan_version_id FROM billing_invoices
                WHERE provider=:provider AND provider_invoice_ref=:invoice_ref
                """),
                {"provider": event.provider, "invoice_ref": event.invoice_ref},
            )
        ).scalar_one_or_none()
        if prior is not None and prior != event.plan_version_id:
            raise BillingError("BILLING_INVOICE_PLAN_VERSION_CONFLICT", 409)
        await session.execute(
            text("""
            INSERT INTO billing_invoices(
              invoice_id, organization_id, provider, provider_invoice_ref,
              plan_version_id, status, amount_due_microusd, currency,
              hosted_invoice_url, created_at
            ) VALUES (
              :invoice_id, :org, :provider, :invoice_ref, :plan, :status,
              :amount, :currency, :url, now()
            )
            ON CONFLICT (provider, provider_invoice_ref) DO UPDATE SET
              status=EXCLUDED.status,
              amount_due_microusd=EXCLUDED.amount_due_microusd,
              currency=EXCLUDED.currency,
              hosted_invoice_url=EXCLUDED.hosted_invoice_url
            """),
            {
                "invoice_id": f"invoice-{event.provider}-{event.invoice_ref}",
                "org": event.organization_id,
                "provider": event.provider,
                "invoice_ref": event.invoice_ref,
                "plan": event.plan_version_id,
                "status": status,
                "amount": event.amount_due_microusd,
                "currency": event.currency,
                "url": event.hosted_invoice_url,
            },
        )
        if event.event_type == "INVOICE_PAID" and plan.monthly_credit_grant > 0:
            await session.execute(
                text("""
                INSERT INTO billing_credit_ledger(
                  entry_id, organization_id, entry_type, delta_credits,
                  source_type, source_id, idempotency_key, created_at
                ) VALUES (
                  :entry_id, :org, 'GRANT', :credits, 'INVOICE', :source,
                  :idempotency_key, now()
                )
                ON CONFLICT (organization_id, idempotency_key) DO NOTHING
                """),
                {
                    "entry_id": str(uuid4()),
                    "org": event.organization_id,
                    "credits": plan.monthly_credit_grant,
                    "source": event.invoice_ref,
                    "idempotency_key": (
                        f"invoice:{event.provider}:{event.invoice_ref}:"
                        f"{event.plan_version_id}:credit-grant"
                    ),
                },
            )


def load_stripe_runtime_config(
    *, environment: str
) -> tuple[StripeProviderConfig, tuple[PlanVersion, ...]]:
    required = {
        "LUMI_STRIPE_SECRET_KEY": os.environ.get("LUMI_STRIPE_SECRET_KEY", ""),
        "LUMI_STRIPE_WEBHOOK_SECRET": os.environ.get("LUMI_STRIPE_WEBHOOK_SECRET", ""),
        "LUMI_STRIPE_CHECKOUT_SUCCESS_URL": os.environ.get(
            "LUMI_STRIPE_CHECKOUT_SUCCESS_URL", ""
        ),
        "LUMI_STRIPE_CHECKOUT_CANCEL_URL": os.environ.get(
            "LUMI_STRIPE_CHECKOUT_CANCEL_URL", ""
        ),
        "LUMI_STRIPE_PORTAL_RETURN_URL": os.environ.get("LUMI_STRIPE_PORTAL_RETURN_URL", ""),
        "LUMI_STRIPE_PLAN_CATALOG_JSON": os.environ.get("LUMI_STRIPE_PLAN_CATALOG_JSON", ""),
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise RuntimeError("Stripe billing configuration missing: " + ", ".join(sorted(missing)))
    try:
        raw_catalog = json.loads(required["LUMI_STRIPE_PLAN_CATALOG_JSON"])
    except json.JSONDecodeError as error:
        raise RuntimeError("LUMI_STRIPE_PLAN_CATALOG_JSON is invalid JSON") from error
    if not isinstance(raw_catalog, list) or not raw_catalog:
        raise RuntimeError("LUMI_STRIPE_PLAN_CATALOG_JSON must be a non-empty array")
    plans: list[PlanVersion] = []
    price_map: dict[str, str] = {}
    for raw in raw_catalog:
        if not isinstance(raw, dict):
            raise RuntimeError("Stripe plan catalog entries must be objects")
        price_id = raw.get("stripe_price_id")
        if not isinstance(price_id, str) or not price_id.startswith("price_"):
            raise RuntimeError("every Stripe plan catalog entry needs stripe_price_id")
        plan = PlanVersion(
            plan_id=str(raw["plan_id"]),
            plan_version_id=str(raw["plan_version_id"]),
            version=int(raw["version"]),
            name=str(raw["name"]),
            currency=str(raw["currency"]).upper(),
            price_microusd=int(raw["price_microusd"]),
            billing_interval=str(raw["billing_interval"]).upper(),  # type: ignore[arg-type]
            monthly_credit_grant=int(raw["monthly_credit_grant"]),
            entitlements=dict(raw.get("entitlements", {})),
            status=str(raw.get("status", "ACTIVE")).upper(),  # type: ignore[arg-type]
        )
        if plan.currency != "USD":
            raise RuntimeError("Stripe billing V1 supports USD plans only")
        if plan.price_microusd % 10_000 != 0:
            raise RuntimeError("Stripe USD price_microusd must resolve to whole cents")
        if plan.plan_version_id in price_map:
            raise RuntimeError(f"duplicate plan_version_id: {plan.plan_version_id}")
        plans.append(plan)
        price_map[plan.plan_version_id] = price_id
    expected_livemode = environment == "production"
    return (
        StripeProviderConfig(
            secret_key=required["LUMI_STRIPE_SECRET_KEY"],
            webhook_secret=required["LUMI_STRIPE_WEBHOOK_SECRET"],
            price_ids_by_plan_version=price_map,
            checkout_success_url=required["LUMI_STRIPE_CHECKOUT_SUCCESS_URL"],
            checkout_cancel_url=required["LUMI_STRIPE_CHECKOUT_CANCEL_URL"],
            portal_return_url=required["LUMI_STRIPE_PORTAL_RETURN_URL"],
            expected_livemode=expected_livemode,
        ),
        tuple(plans),
    )


async def _set_tenant(session: AsyncSession, organization_id: str) -> None:
    try:
        UUID(organization_id)
    except ValueError as error:
        raise BillingError("BILLING_ORGANIZATION_ID_INVALID", 400) from error
    await session.execute(
        text("SELECT set_config('app.current_organization_id', :org, true)"),
        {"org": organization_id},
    )


def _require(actor: BillingActor, permission: str) -> None:
    if permission not in actor.permissions:
        raise BillingError("BILLING_FORBIDDEN", 403)


def _plan_params(plan: PlanVersion) -> dict[str, Any]:
    return {
        "plan_version_id": plan.plan_version_id,
        "plan_id": plan.plan_id,
        "version": plan.version,
        "name": plan.name,
        "currency": plan.currency,
        "price_microusd": plan.price_microusd,
        "billing_interval": plan.billing_interval,
        "monthly_credit_grant": plan.monthly_credit_grant,
        "status": plan.status,
    }


def _plan_from_row(row: Mapping[str, Any]) -> PlanVersion:
    return PlanVersion(
        plan_id=row["plan_id"],
        plan_version_id=row["plan_version_id"],
        version=row["version"],
        name=row["name"],
        currency=row["currency"],
        price_microusd=row["price_microusd"],
        billing_interval=row["billing_interval"],
        monthly_credit_grant=row["monthly_credit_grant"],
        entitlements=dict(row["entitlements"] or {}),
        status=row["status"],
    )


async def _get_plan(session: AsyncSession, plan_version_id: str) -> PlanVersion | None:
    row = (
        await session.execute(
            text("SELECT * FROM billing_plan_versions WHERE plan_version_id=:id"),
            {"id": plan_version_id},
        )
    ).mappings().first()
    return None if row is None else _plan_from_row(row)


async def _list_active_plans(session: AsyncSession) -> tuple[PlanVersion, ...]:
    rows = (
        await session.execute(
            text("SELECT * FROM billing_plan_versions WHERE status='ACTIVE' ORDER BY name, version")
        )
    ).mappings().all()
    return tuple(_plan_from_row(row) for row in rows)


async def _get_account(session: AsyncSession, organization_id: str) -> BillingAccount | None:
    row = (
        await session.execute(
            text("SELECT * FROM billing_accounts WHERE organization_id=:org"),
            {"org": organization_id},
        )
    ).mappings().first()
    if row is None:
        return None
    return BillingAccount(
        organization_id=str(row["organization_id"]),
        payment_provider=row["payment_provider"],
        payment_customer_ref=row["payment_customer_ref"],
        created_at=row["created_at"].isoformat(),
    )


async def _get_subscription(session: AsyncSession, organization_id: str) -> Subscription | None:
    row = (
        await session.execute(
            text("SELECT * FROM billing_subscriptions WHERE organization_id=:org"),
            {"org": organization_id},
        )
    ).mappings().first()
    if row is None:
        return None
    return Subscription(
        subscription_id=row["subscription_id"],
        organization_id=str(row["organization_id"]),
        plan_version_id=row["plan_version_id"],
        payment_provider=row["payment_provider"],
        provider_subscription_ref=row["provider_subscription_ref"],
        state=row["state"],
        current_period_start=_iso(row["current_period_start"]),
        current_period_end=_iso(row["current_period_end"]),
        cancel_at_period_end=row["cancel_at_period_end"],
    )


async def _credit_balance(session: AsyncSession, organization_id: str) -> int:
    value = await session.scalar(
        text(
            "SELECT COALESCE(sum(delta_credits),0) FROM billing_credit_ledger "
            "WHERE organization_id=:org"
        ),
        {"org": organization_id},
    )
    return int(value or 0)


async def _list_credits(
    session: AsyncSession, organization_id: str, *, limit: int
) -> tuple[CreditLedgerEntry, ...]:
    rows = (
        await session.execute(
            text("""
            SELECT * FROM billing_credit_ledger
            WHERE organization_id=:org ORDER BY created_at DESC LIMIT :limit
            """),
            {"org": organization_id, "limit": limit},
        )
    ).mappings().all()
    return tuple(
        CreditLedgerEntry(
            entry_id=str(row["entry_id"]),
            organization_id=str(row["organization_id"]),
            entry_type=row["entry_type"],
            delta_credits=row["delta_credits"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            pricing_policy_version=row["pricing_policy_version"],
            idempotency_key=row["idempotency_key"],
            created_at=row["created_at"].isoformat(),
            project_id=str(row["project_id"]) if row["project_id"] else None,
            usage_record_id=row["usage_record_id"],
            reverses_entry_id=(
                str(row["reverses_entry_id"]) if row["reverses_entry_id"] else None
            ),
        )
        for row in rows
    )


async def _list_invoices(
    session: AsyncSession, organization_id: str, *, limit: int
) -> tuple[InvoiceRef, ...]:
    rows = (
        await session.execute(
            text("""
            SELECT * FROM billing_invoices
            WHERE organization_id=:org ORDER BY created_at DESC LIMIT :limit
            """),
            {"org": organization_id, "limit": limit},
        )
    ).mappings().all()
    return tuple(
        InvoiceRef(
            invoice_id=row["invoice_id"],
            organization_id=str(row["organization_id"]),
            provider=row["provider"],
            provider_invoice_ref=row["provider_invoice_ref"],
            plan_version_id=row["plan_version_id"],
            status=row["status"],
            amount_due_microusd=row["amount_due_microusd"],
            currency=row["currency"],
            hosted_invoice_url=row["hosted_invoice_url"],
            created_at=row["created_at"].isoformat(),
        )
        for row in rows
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()
