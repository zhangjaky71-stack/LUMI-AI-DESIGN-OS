from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterator, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .contracts import (
    BillingConflict,
    BillingNotFound,
    CreditEventType,
    CreditLedgerEntry,
    CreditWalletRecord,
    InsufficientCredits,
    NormalizedPaymentEvent,
    PaymentEventStatus,
    PlanVersionRecord,
    SubscriptionRecord,
    SubscriptionState,
)


class PostgresBillingRepository:
    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def _assert_org(self, organization_id: UUID) -> None:
        if organization_id != self.organization_id:
            raise BillingNotFound("BILLING_RESOURCE_NOT_FOUND")

    def get_plan_version(self, plan_version_id: UUID) -> PlanVersionRecord:
        row = self.session.execute(
            text(
                """
                SELECT pv.*, p.plan_key, p.name AS plan_name
                FROM billing_plan_versions pv
                JOIN billing_plans p ON p.id=pv.plan_id
                WHERE pv.id=:plan_version_id AND p.active=true
                """
            ),
            {"plan_version_id": plan_version_id},
        ).mappings().one_or_none()
        if row is None:
            raise BillingNotFound("BILLING_PLAN_VERSION_NOT_FOUND")
        return self._plan(row)

    def find_plan_version(self, plan_key: str, version: int) -> PlanVersionRecord:
        row = self.session.execute(
            text(
                """
                SELECT pv.*, p.plan_key, p.name AS plan_name
                FROM billing_plan_versions pv
                JOIN billing_plans p ON p.id=pv.plan_id
                WHERE p.plan_key=:plan_key AND pv.version=:version
                """
            ),
            {"plan_key": plan_key, "version": version},
        ).mappings().one_or_none()
        if row is None:
            raise BillingNotFound("BILLING_PLAN_VERSION_NOT_FOUND")
        return self._plan(row)

    def ensure_billing_account(
        self, *, provider: str, provider_customer_ref: str
    ) -> UUID:
        row = self.session.execute(
            text(
                """
                SELECT id FROM billing_accounts
                WHERE organization_id=:organization_id AND provider=:provider
                """
            ),
            {"organization_id": self.organization_id, "provider": provider},
        ).mappings().one_or_none()
        if row is not None:
            return UUID(str(row["id"]))
        account_id = new_uuid7()
        now = datetime.now(UTC)
        with self._transaction():
            self.session.execute(
                text(
                    """
                    INSERT INTO billing_accounts (
                        id, organization_id, provider, provider_customer_ref,
                        status, created_at, updated_at, version
                    ) VALUES (
                        :id, :organization_id, :provider, :provider_customer_ref,
                        'ACTIVE', :now, :now, 1
                    ) ON CONFLICT (organization_id, provider) DO NOTHING
                    """
                ),
                {
                    "id": account_id,
                    "organization_id": self.organization_id,
                    "provider": provider,
                    "provider_customer_ref": provider_customer_ref,
                    "now": now,
                },
            )
        row = self.session.execute(
            text(
                "SELECT id FROM billing_accounts WHERE organization_id=:organization_id AND provider=:provider"
            ),
            {"organization_id": self.organization_id, "provider": provider},
        ).mappings().one()
        return UUID(str(row["id"]))

    def get_customer_ref(self, provider: str) -> str | None:
        row = self.session.execute(
            text(
                """
                SELECT provider_customer_ref FROM billing_accounts
                WHERE organization_id=:organization_id AND provider=:provider AND status='ACTIVE'
                """
            ),
            {"organization_id": self.organization_id, "provider": provider},
        ).mappings().one_or_none()
        return None if row is None else str(row["provider_customer_ref"])

    def get_subscription(self) -> SubscriptionRecord | None:
        row = self.session.execute(
            text(
                """
                SELECT * FROM billing_subscriptions
                WHERE organization_id=:organization_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"organization_id": self.organization_id},
        ).mappings().one_or_none()
        return None if row is None else self._subscription(row)

    def get_subscription_plan(self, subscription: SubscriptionRecord) -> PlanVersionRecord:
        return self.get_plan_version(subscription.plan_version_id)

    def ensure_wallet(self, *, allow_postpaid: bool = False) -> CreditWalletRecord:
        row = self.session.execute(
            text(
                "SELECT * FROM billing_credit_wallets WHERE organization_id=:organization_id"
            ),
            {"organization_id": self.organization_id},
        ).mappings().one_or_none()
        if row is None:
            wallet_id = new_uuid7()
            now = datetime.now(UTC)
            with self._transaction():
                self.session.execute(
                    text(
                        """
                        INSERT INTO billing_credit_wallets (
                            id, organization_id, cached_balance, allow_postpaid,
                            created_at, updated_at, version
                        ) VALUES (:id, :organization_id, 0, :allow_postpaid, :now, :now, 1)
                        ON CONFLICT (organization_id) DO NOTHING
                        """
                    ),
                    {
                        "id": wallet_id,
                        "organization_id": self.organization_id,
                        "allow_postpaid": allow_postpaid,
                        "now": now,
                    },
                )
            row = self.session.execute(
                text(
                    "SELECT * FROM billing_credit_wallets WHERE organization_id=:organization_id"
                ),
                {"organization_id": self.organization_id},
            ).mappings().one()
        return self._wallet(row)

    def append_credit(
        self,
        *,
        operation_id: UUID,
        event_type: CreditEventType,
        amount: Decimal,
        reason: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        pricing_policy_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CreditLedgerEntry:
        existing = self._credit_by_operation(operation_id)
        if existing is not None:
            if existing.event_type != event_type or existing.amount != amount:
                raise BillingConflict("BILLING_CREDIT_OPERATION_CONFLICT")
            return existing
        now = datetime.now(UTC)
        entry_id = new_uuid7()
        with self._transaction():
            wallet = self.session.execute(
                text(
                    """
                    SELECT * FROM billing_credit_wallets
                    WHERE organization_id=:organization_id
                    FOR UPDATE
                    """
                ),
                {"organization_id": self.organization_id},
            ).mappings().one_or_none()
            if wallet is None:
                wallet_id = new_uuid7()
                self.session.execute(
                    text(
                        """
                        INSERT INTO billing_credit_wallets (
                            id, organization_id, cached_balance, allow_postpaid,
                            created_at, updated_at, version
                        ) VALUES (:id, :organization_id, 0, false, :now, :now, 1)
                        """
                    ),
                    {"id": wallet_id, "organization_id": self.organization_id, "now": now},
                )
                wallet = self.session.execute(
                    text(
                        """
                        SELECT * FROM billing_credit_wallets
                        WHERE organization_id=:organization_id FOR UPDATE
                        """
                    ),
                    {"organization_id": self.organization_id},
                ).mappings().one()
            current = Decimal(wallet["cached_balance"])
            next_balance = current + amount
            if next_balance < 0 and not bool(wallet["allow_postpaid"]):
                raise InsufficientCredits("BILLING_INSUFFICIENT_CREDITS")
            self.session.execute(
                text(
                    """
                    INSERT INTO billing_credit_ledger (
                        id, organization_id, wallet_id, operation_id, event_type,
                        amount, reason, reference_type, reference_id,
                        pricing_policy_version, metadata_json, created_at
                    ) VALUES (
                        :id, :organization_id, :wallet_id, :operation_id, :event_type,
                        :amount, :reason, :reference_type, :reference_id,
                        :pricing_policy_version, CAST(:metadata_json AS jsonb), :now
                    )
                    """
                ),
                {
                    "id": entry_id,
                    "organization_id": self.organization_id,
                    "wallet_id": wallet["id"],
                    "operation_id": operation_id,
                    "event_type": event_type.value,
                    "amount": amount,
                    "reason": reason,
                    "reference_type": reference_type,
                    "reference_id": reference_id,
                    "pricing_policy_version": pricing_policy_version,
                    "metadata_json": json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
                    "now": now,
                },
            )
            self.session.execute(
                text(
                    """
                    UPDATE billing_credit_wallets
                    SET cached_balance=:balance, updated_at=:now, version=version+1
                    WHERE id=:wallet_id AND organization_id=:organization_id
                    """
                ),
                {
                    "balance": next_balance,
                    "now": now,
                    "wallet_id": wallet["id"],
                    "organization_id": self.organization_id,
                },
            )
        result = self._credit_by_operation(operation_id)
        if result is None:
            raise BillingConflict("BILLING_CREDIT_WRITE_LOST")
        return result

    def list_credits(self, *, limit: int = 100) -> tuple[CreditLedgerEntry, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("BILLING_CREDIT_LIST_LIMIT_INVALID")
        rows = self.session.execute(
            text(
                """
                SELECT * FROM billing_credit_ledger
                WHERE organization_id=:organization_id
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"organization_id": self.organization_id, "limit": limit},
        ).mappings().all()
        return tuple(self._credit(row) for row in rows)

    def claim_payment_event(
        self, event: NormalizedPaymentEvent, *, body_sha256: str
    ) -> PaymentEventStatus:
        self._assert_org(event.organization_id)
        with self._transaction():
            try:
                self.session.execute(
                    text(
                        """
                        INSERT INTO billing_payment_events (
                            id, organization_id, provider, provider_event_id, event_type,
                            body_sha256, status, occurred_at, created_at, updated_at
                        ) VALUES (
                            :id, :organization_id, :provider, :provider_event_id, :event_type,
                            :body_sha256, 'RECEIVED', :occurred_at, :now, :now
                        )
                        """
                    ),
                    {
                        "id": new_uuid7(),
                        "organization_id": self.organization_id,
                        "provider": event.provider,
                        "provider_event_id": event.provider_event_id,
                        "event_type": event.event_type,
                        "body_sha256": body_sha256,
                        "occurred_at": event.occurred_at,
                        "now": datetime.now(UTC),
                    },
                )
            except IntegrityError:
                self.session.rollback()
        row = self.session.execute(
            text(
                """
                SELECT status, body_sha256 FROM billing_payment_events
                WHERE provider=:provider AND provider_event_id=:provider_event_id
                """
            ),
            {"provider": event.provider, "provider_event_id": event.provider_event_id},
        ).mappings().one_or_none()
        if row is None:
            raise BillingConflict("BILLING_PAYMENT_EVENT_CLAIM_FAILED")
        if str(row["body_sha256"]) != body_sha256:
            raise BillingConflict("BILLING_PAYMENT_EVENT_BODY_CONFLICT")
        return PaymentEventStatus(str(row["status"]))

    def apply_payment_event(self, event: NormalizedPaymentEvent) -> PaymentEventStatus:
        self._assert_org(event.organization_id)
        with self._transaction():
            payment_event = self.session.execute(
                text(
                    """
                    SELECT * FROM billing_payment_events
                    WHERE provider=:provider AND provider_event_id=:provider_event_id
                    FOR UPDATE
                    """
                ),
                {"provider": event.provider, "provider_event_id": event.provider_event_id},
            ).mappings().one_or_none()
            if payment_event is None:
                raise BillingConflict("BILLING_PAYMENT_EVENT_NOT_CLAIMED")
            current_status = PaymentEventStatus(str(payment_event["status"]))
            if current_status == PaymentEventStatus.APPLIED:
                return current_status
            if current_status == PaymentEventStatus.REJECTED:
                raise BillingConflict("BILLING_PAYMENT_EVENT_REJECTED")

            plan: PlanVersionRecord | None = None
            if event.plan_key is not None or event.plan_version is not None:
                if event.plan_key is None or event.plan_version is None:
                    raise BillingConflict("BILLING_PAYMENT_EVENT_PLAN_PAIR_REQUIRED")
                plan = self.find_plan_version(event.plan_key, event.plan_version)

            account_id = self._account_id_for_event(event)
            if event.subscription_ref is not None:
                if plan is None or event.subscription_state is None:
                    raise BillingConflict("BILLING_SUBSCRIPTION_EVENT_INCOMPLETE")
                self._upsert_subscription(account_id=account_id, plan=plan, event=event)
                self.session.execute(
                    text(
                        """
                        UPDATE billing_credit_wallets
                        SET allow_postpaid=:allow_postpaid, updated_at=:now, version=version+1
                        WHERE organization_id=:organization_id
                        """
                    ),
                    {
                        "allow_postpaid": plan.postpaid_allowed,
                        "now": datetime.now(UTC),
                        "organization_id": self.organization_id,
                    },
                )

            if event.invoice_ref is not None:
                self._upsert_invoice(account_id=account_id, event=event)

            if event.credit_grant is not None and event.credit_grant > 0:
                operation_id = uuid5(
                    NAMESPACE_URL,
                    f"lumi:billing-credit:{event.provider}:{event.provider_event_id}",
                )
                self._append_credit_in_transaction(
                    operation_id=operation_id,
                    event_type=CreditEventType.GRANT,
                    amount=event.credit_grant,
                    reason="payment_event_credit_grant",
                    reference_type="payment_event",
                    reference_id=event.provider_event_id,
                    pricing_policy_version=(
                        f"{event.plan_key}:v{event.plan_version}"
                        if event.plan_key and event.plan_version
                        else None
                    ),
                )

            now = datetime.now(UTC)
            self.session.execute(
                text(
                    """
                    UPDATE billing_payment_events
                    SET status='APPLIED', processed_at=:now, updated_at=:now
                    WHERE id=:id
                    """
                ),
                {"now": now, "id": payment_event["id"]},
            )
        return PaymentEventStatus.APPLIED

    def mark_payment_event_rejected(self, event: NormalizedPaymentEvent, reason: str) -> None:
        self._assert_org(event.organization_id)
        with self._transaction():
            self.session.execute(
                text(
                    """
                    UPDATE billing_payment_events
                    SET status='REJECTED', rejection_code=:reason, updated_at=:now
                    WHERE provider=:provider AND provider_event_id=:provider_event_id
                      AND status <> 'APPLIED'
                    """
                ),
                {
                    "reason": reason[:160],
                    "now": datetime.now(UTC),
                    "provider": event.provider,
                    "provider_event_id": event.provider_event_id,
                },
            )

    def list_invoices(self, *, limit: int = 100) -> tuple[Mapping[str, Any], ...]:
        rows = self.session.execute(
            text(
                """
                SELECT provider_invoice_ref, status, amount_due, currency,
                       hosted_invoice_url, period_start, period_end, created_at, updated_at
                FROM billing_invoice_refs
                WHERE organization_id=:organization_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"organization_id": self.organization_id, "limit": limit},
        ).mappings().all()
        return tuple(rows)

    def _account_id_for_event(self, event: NormalizedPaymentEvent) -> UUID:
        row = self.session.execute(
            text(
                """
                SELECT id FROM billing_accounts
                WHERE organization_id=:organization_id AND provider=:provider
                FOR UPDATE
                """
            ),
            {"organization_id": self.organization_id, "provider": event.provider},
        ).mappings().one_or_none()
        if row is not None:
            return UUID(str(row["id"]))
        customer_ref = event.metadata.get("customer_ref")
        if not isinstance(customer_ref, str) or not customer_ref:
            raise BillingConflict("BILLING_PAYMENT_CUSTOMER_REF_REQUIRED")
        account_id = new_uuid7()
        now = datetime.now(UTC)
        self.session.execute(
            text(
                """
                INSERT INTO billing_accounts (
                    id, organization_id, provider, provider_customer_ref,
                    status, created_at, updated_at, version
                ) VALUES (:id, :organization_id, :provider, :customer_ref, 'ACTIVE', :now, :now, 1)
                """
            ),
            {
                "id": account_id,
                "organization_id": self.organization_id,
                "provider": event.provider,
                "customer_ref": customer_ref,
                "now": now,
            },
        )
        return account_id

    def _upsert_subscription(
        self,
        *,
        account_id: UUID,
        plan: PlanVersionRecord,
        event: NormalizedPaymentEvent,
    ) -> None:
        now = datetime.now(UTC)
        self.session.execute(
            text(
                """
                INSERT INTO billing_subscriptions (
                    id, organization_id, billing_account_id, plan_version_id,
                    provider, provider_subscription_ref, state,
                    current_period_start, current_period_end, cancel_at_period_end,
                    created_at, updated_at, version
                ) VALUES (
                    :id, :organization_id, :account_id, :plan_version_id,
                    :provider, :subscription_ref, :state,
                    :period_start, :period_end, :cancel_at_period_end,
                    :now, :now, 1
                )
                ON CONFLICT (provider, provider_subscription_ref) DO UPDATE SET
                    plan_version_id=EXCLUDED.plan_version_id,
                    state=EXCLUDED.state,
                    current_period_start=EXCLUDED.current_period_start,
                    current_period_end=EXCLUDED.current_period_end,
                    cancel_at_period_end=EXCLUDED.cancel_at_period_end,
                    updated_at=EXCLUDED.updated_at,
                    version=billing_subscriptions.version+1
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": self.organization_id,
                "account_id": account_id,
                "plan_version_id": plan.id,
                "provider": event.provider,
                "subscription_ref": event.subscription_ref,
                "state": event.subscription_state.value if event.subscription_state else None,
                "period_start": event.current_period_start,
                "period_end": event.current_period_end,
                "cancel_at_period_end": event.subscription_state == SubscriptionState.CANCEL_AT_PERIOD_END,
                "now": now,
            },
        )

    def _upsert_invoice(self, *, account_id: UUID, event: NormalizedPaymentEvent) -> None:
        amount = event.invoice_amount if event.invoice_amount is not None else Decimal("0")
        currency = event.currency or "USD"
        now = datetime.now(UTC)
        self.session.execute(
            text(
                """
                INSERT INTO billing_invoice_refs (
                    id, organization_id, billing_account_id, provider, provider_invoice_ref,
                    status, amount_due, currency, hosted_invoice_url,
                    period_start, period_end, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :account_id, :provider, :invoice_ref,
                    :status, :amount, :currency, :hosted_url,
                    :period_start, :period_end, :now, :now
                )
                ON CONFLICT (provider, provider_invoice_ref) DO UPDATE SET
                    status=EXCLUDED.status,
                    amount_due=EXCLUDED.amount_due,
                    currency=EXCLUDED.currency,
                    hosted_invoice_url=EXCLUDED.hosted_invoice_url,
                    period_start=EXCLUDED.period_start,
                    period_end=EXCLUDED.period_end,
                    updated_at=EXCLUDED.updated_at
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": self.organization_id,
                "account_id": account_id,
                "provider": event.provider,
                "invoice_ref": event.invoice_ref,
                "status": event.invoice_status or "unknown",
                "amount": amount,
                "currency": currency,
                "hosted_url": event.hosted_invoice_url,
                "period_start": event.current_period_start,
                "period_end": event.current_period_end,
                "now": now,
            },
        )

    def _append_credit_in_transaction(
        self,
        *,
        operation_id: UUID,
        event_type: CreditEventType,
        amount: Decimal,
        reason: str,
        reference_type: str | None,
        reference_id: str | None,
        pricing_policy_version: str | None,
    ) -> None:
        existing = self.session.execute(
            text(
                """
                SELECT id FROM billing_credit_ledger
                WHERE organization_id=:organization_id AND operation_id=:operation_id
                """
            ),
            {"organization_id": self.organization_id, "operation_id": operation_id},
        ).mappings().one_or_none()
        if existing is not None:
            return
        wallet = self.session.execute(
            text(
                """
                SELECT * FROM billing_credit_wallets
                WHERE organization_id=:organization_id FOR UPDATE
                """
            ),
            {"organization_id": self.organization_id},
        ).mappings().one_or_none()
        now = datetime.now(UTC)
        if wallet is None:
            wallet_id = new_uuid7()
            self.session.execute(
                text(
                    """
                    INSERT INTO billing_credit_wallets (
                        id, organization_id, cached_balance, allow_postpaid,
                        created_at, updated_at, version
                    ) VALUES (:id, :organization_id, 0, false, :now, :now, 1)
                    """
                ),
                {"id": wallet_id, "organization_id": self.organization_id, "now": now},
            )
            wallet = self.session.execute(
                text(
                    "SELECT * FROM billing_credit_wallets WHERE id=:id FOR UPDATE"
                ),
                {"id": wallet_id},
            ).mappings().one()
        next_balance = Decimal(wallet["cached_balance"]) + amount
        if next_balance < 0 and not bool(wallet["allow_postpaid"]):
            raise InsufficientCredits("BILLING_INSUFFICIENT_CREDITS")
        self.session.execute(
            text(
                """
                INSERT INTO billing_credit_ledger (
                    id, organization_id, wallet_id, operation_id, event_type,
                    amount, reason, reference_type, reference_id,
                    pricing_policy_version, metadata_json, created_at
                ) VALUES (
                    :id, :organization_id, :wallet_id, :operation_id, :event_type,
                    :amount, :reason, :reference_type, :reference_id,
                    :pricing_policy_version, '{}'::jsonb, :now
                )
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": self.organization_id,
                "wallet_id": wallet["id"],
                "operation_id": operation_id,
                "event_type": event_type.value,
                "amount": amount,
                "reason": reason,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "pricing_policy_version": pricing_policy_version,
                "now": now,
            },
        )
        self.session.execute(
            text(
                """
                UPDATE billing_credit_wallets
                SET cached_balance=:balance, updated_at=:now, version=version+1
                WHERE id=:id
                """
            ),
            {"balance": next_balance, "now": now, "id": wallet["id"]},
        )

    def _credit_by_operation(self, operation_id: UUID) -> CreditLedgerEntry | None:
        row = self.session.execute(
            text(
                """
                SELECT * FROM billing_credit_ledger
                WHERE organization_id=:organization_id AND operation_id=:operation_id
                """
            ),
            {"organization_id": self.organization_id, "operation_id": operation_id},
        ).mappings().one_or_none()
        return None if row is None else self._credit(row)

    @staticmethod
    def _plan(row: Mapping[str, Any]) -> PlanVersionRecord:
        return PlanVersionRecord(
            id=row["id"],
            plan_id=row["plan_id"],
            plan_key=str(row["plan_key"]),
            plan_name=str(row["plan_name"]),
            version=int(row["version"]),
            currency=str(row["currency"]),
            monthly_price=Decimal(row["monthly_price"]),
            included_credits=Decimal(row["included_credits"]),
            postpaid_allowed=bool(row["postpaid_allowed"]),
            entitlements=dict(row["entitlements_json"] or {}),
            pricing_policy=dict(row["pricing_policy_json"] or {}),
            effective_at=row["effective_at"],
            retired_at=row["retired_at"],
        )

    @staticmethod
    def _subscription(row: Mapping[str, Any]) -> SubscriptionRecord:
        return SubscriptionRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            billing_account_id=row["billing_account_id"],
            plan_version_id=row["plan_version_id"],
            provider=str(row["provider"]),
            provider_subscription_ref=str(row["provider_subscription_ref"]),
            state=SubscriptionState(str(row["state"])),
            current_period_start=row["current_period_start"],
            current_period_end=row["current_period_end"],
            cancel_at_period_end=bool(row["cancel_at_period_end"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _wallet(row: Mapping[str, Any]) -> CreditWalletRecord:
        return CreditWalletRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            balance=Decimal(row["cached_balance"]),
            allow_postpaid=bool(row["allow_postpaid"]),
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _credit(row: Mapping[str, Any]) -> CreditLedgerEntry:
        return CreditLedgerEntry(
            id=row["id"],
            organization_id=row["organization_id"],
            wallet_id=row["wallet_id"],
            operation_id=row["operation_id"],
            event_type=CreditEventType(str(row["event_type"])),
            amount=Decimal(row["amount"]),
            reason=str(row["reason"]),
            reference_type=row["reference_type"],
            reference_id=row["reference_id"],
            pricing_policy_version=row["pricing_policy_version"],
            metadata=dict(row["metadata_json"] or {}),
            created_at=row["created_at"],
        )
