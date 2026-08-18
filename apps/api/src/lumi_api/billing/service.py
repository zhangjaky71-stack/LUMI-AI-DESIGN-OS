from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from .contracts import (
    BillingConflict,
    BillingForbidden,
    BillingOverview,
    CheckoutSession,
    CreditEventType,
    CreditLedgerEntry,
    EntitlementSnapshot,
    NormalizedPaymentEvent,
    PaymentEventStatus,
    PaymentProvider,
    PlanVersionRecord,
    PortalSession,
    SubscriptionState,
    require_positive_credit_amount,
)
from .repository import PostgresBillingRepository

_ACTIVE_ENTITLEMENT_STATES = {
    SubscriptionState.TRIALING,
    SubscriptionState.ACTIVE,
    SubscriptionState.PAST_DUE,
    SubscriptionState.CANCEL_AT_PERIOD_END,
}


class BillingService:
    def __init__(
        self,
        repository: PostgresBillingRepository,
        provider: PaymentProvider,
    ) -> None:
        self.repository = repository
        self.provider = provider

    @staticmethod
    def _require_permission(permissions: tuple[str, ...], permission: str) -> None:
        if permission not in permissions:
            raise BillingForbidden("BILLING_PERMISSION_DENIED")

    def overview(self, *, permissions: tuple[str, ...]) -> BillingOverview:
        self._require_permission(permissions, "billing.read")
        wallet = self.repository.ensure_wallet()
        subscription = self.repository.get_subscription()
        plan = (
            self.repository.get_subscription_plan(subscription)
            if subscription is not None
            else None
        )
        entitlements = self._entitlements(wallet.balance, subscription, plan)
        return BillingOverview(
            organization_id=self.repository.organization_id,
            plan=plan,
            subscription=subscription,
            wallet=wallet,
            entitlements=entitlements,
        )

    def entitlements(self, *, permissions: tuple[str, ...]) -> EntitlementSnapshot:
        self._require_permission(permissions, "billing.read")
        wallet = self.repository.ensure_wallet()
        subscription = self.repository.get_subscription()
        plan = (
            self.repository.get_subscription_plan(subscription)
            if subscription is not None
            else None
        )
        return self._entitlements(wallet.balance, subscription, plan)

    def create_checkout(
        self,
        *,
        permissions: tuple[str, ...],
        plan_version_id: UUID,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        self._require_permission(permissions, "billing.manage")
        plan = self.repository.get_plan_version(plan_version_id)
        customer_ref = self.repository.get_customer_ref(self.provider.name)
        if customer_ref is None:
            customer_ref = self.provider.create_customer(
                organization_id=self.repository.organization_id
            )
            self.repository.ensure_billing_account(
                provider=self.provider.name,
                provider_customer_ref=customer_ref,
            )
        return self.provider.create_checkout(
            organization_id=self.repository.organization_id,
            provider_customer_ref=customer_ref,
            plan_version=plan,
            success_url=success_url,
            cancel_url=cancel_url,
        )

    def create_portal(
        self,
        *,
        permissions: tuple[str, ...],
        return_url: str,
    ) -> PortalSession:
        self._require_permission(permissions, "billing.manage")
        customer_ref = self.repository.get_customer_ref(self.provider.name)
        if customer_ref is None:
            raise BillingConflict("BILLING_CUSTOMER_NOT_CREATED")
        return self.provider.create_portal_session(
            provider_customer_ref=customer_ref,
            return_url=return_url,
        )

    def consume_credits(
        self,
        *,
        operation_id: UUID,
        amount: Decimal,
        reason: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        pricing_policy_version: str | None = None,
    ) -> CreditLedgerEntry:
        amount = require_positive_credit_amount(amount)
        return self.repository.append_credit(
            operation_id=operation_id,
            event_type=CreditEventType.CONSUME,
            amount=-amount,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            pricing_policy_version=pricing_policy_version,
        )

    def refund_credits(
        self,
        *,
        operation_id: UUID,
        amount: Decimal,
        reason: str,
        reference_id: str | None = None,
    ) -> CreditLedgerEntry:
        amount = require_positive_credit_amount(amount)
        return self.repository.append_credit(
            operation_id=operation_id,
            event_type=CreditEventType.REFUND,
            amount=amount,
            reason=reason,
            reference_type="refund",
            reference_id=reference_id,
        )

    def price_usage(
        self,
        *,
        plan: PlanVersionRecord,
        metric: str,
        quantity: Decimal,
    ) -> tuple[Decimal, str]:
        if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity < 0:
            raise ValueError("BILLING_USAGE_QUANTITY_INVALID")
        policy = plan.pricing_policy
        version = str(policy.get("version") or f"{plan.plan_key}:v{plan.version}")
        rates = policy.get("rates", {})
        if not isinstance(rates, dict) or metric not in rates:
            raise BillingConflict("BILLING_PRICING_RATE_NOT_FOUND")
        raw_rate = rates[metric]
        if isinstance(raw_rate, float):
            raise ValueError("BILLING_PRICING_FLOAT_FORBIDDEN")
        try:
            rate = Decimal(str(raw_rate))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("BILLING_PRICING_RATE_INVALID") from exc
        if not rate.is_finite() or rate < 0:
            raise ValueError("BILLING_PRICING_RATE_INVALID")
        return quantity * rate, version

    def apply_verified_payment_event(
        self,
        event: NormalizedPaymentEvent,
        *,
        body_sha256: str,
    ) -> PaymentEventStatus:
        status = self.repository.claim_payment_event(event, body_sha256=body_sha256)
        if status == PaymentEventStatus.APPLIED:
            return status
        try:
            return self.repository.apply_payment_event(event)
        except Exception as exc:
            self.repository.mark_payment_event_rejected(event, type(exc).__name__)
            raise

    def list_credits(
        self, *, permissions: tuple[str, ...], limit: int = 100
    ) -> tuple[CreditLedgerEntry, ...]:
        self._require_permission(permissions, "billing.read")
        return self.repository.list_credits(limit=limit)

    def list_invoices(self, *, permissions: tuple[str, ...], limit: int = 100):
        self._require_permission(permissions, "billing.read")
        return self.repository.list_invoices(limit=limit)

    @staticmethod
    def body_hash(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def _entitlements(self, balance, subscription, plan) -> EntitlementSnapshot:
        if subscription is None or plan is None:
            return EntitlementSnapshot(
                organization_id=self.repository.organization_id,
                subscription_state=None,
                plan_version_id=None,
                entitlements={},
                credits_balance=balance,
                can_consume_paid_features=False,
            )
        now = datetime.now(UTC)
        active = subscription.state in _ACTIVE_ENTITLEMENT_STATES
        if (
            subscription.state == SubscriptionState.CANCEL_AT_PERIOD_END
            and subscription.current_period_end is not None
            and subscription.current_period_end <= now
        ):
            active = False
        if subscription.state in {
            SubscriptionState.CANCELLED,
            SubscriptionState.INCOMPLETE,
        }:
            active = False
        return EntitlementSnapshot(
            organization_id=self.repository.organization_id,
            subscription_state=subscription.state,
            plan_version_id=plan.id,
            entitlements=plan.entitlements if active else {},
            credits_balance=balance,
            can_consume_paid_features=active and (balance > 0 or plan.postpaid_allowed),
        )
