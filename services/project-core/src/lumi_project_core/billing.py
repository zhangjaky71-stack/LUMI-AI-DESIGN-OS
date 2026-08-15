from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from threading import RLock
from typing import Any, Callable, Literal, Protocol
from uuid import uuid4

SubscriptionState = Literal[
    "TRIALING", "ACTIVE", "PAST_DUE", "CANCEL_AT_PERIOD_END", "CANCELLED", "INCOMPLETE"
]
CreditEntryType = Literal["GRANT", "CONSUME", "REFUND", "EXPIRE", "ADJUSTMENT", "REVERSAL"]
PaymentEventType = Literal[
    "SUBSCRIPTION_CREATED",
    "SUBSCRIPTION_UPDATED",
    "SUBSCRIPTION_CANCELLED",
    "INVOICE_PAID",
    "INVOICE_PAYMENT_FAILED",
]

ACTIVE_ENTITLEMENT_STATES = frozenset({"TRIALING", "ACTIVE", "CANCEL_AT_PERIOD_END"})
VALID_SUBSCRIPTION_STATES = frozenset(
    {"TRIALING", "ACTIVE", "PAST_DUE", "CANCEL_AT_PERIOD_END", "CANCELLED", "INCOMPLETE"}
)
VALID_PAYMENT_EVENT_TYPES = frozenset(
    {
        "SUBSCRIPTION_CREATED",
        "SUBSCRIPTION_UPDATED",
        "SUBSCRIPTION_CANCELLED",
        "INVOICE_PAID",
        "INVOICE_PAYMENT_FAILED",
    }
)


class BillingError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class BillingActor:
    actor_id: str
    organization_id: str
    permissions: frozenset[str]
    billing_email: str | None = None


@dataclass(frozen=True, slots=True)
class PlanVersion:
    plan_id: str
    plan_version_id: str
    version: int
    name: str
    currency: str
    price_microusd: int
    billing_interval: Literal["MONTH", "YEAR"]
    monthly_credit_grant: int
    entitlements: dict[str, int | bool | str]
    status: Literal["ACTIVE", "ARCHIVED"] = "ACTIVE"

    def __post_init__(self) -> None:
        if self.version < 1 or not self.plan_id.strip() or not self.plan_version_id.strip():
            raise BillingError("BILLING_PLAN_VERSION_INVALID")
        if self.price_microusd < 0 or self.monthly_credit_grant < 0:
            raise BillingError("BILLING_PLAN_VALUE_INVALID")
        if len(self.currency) != 3:
            raise BillingError("BILLING_CURRENCY_INVALID")


@dataclass(frozen=True, slots=True)
class BillingAccount:
    organization_id: str
    payment_provider: str
    payment_customer_ref: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Subscription:
    subscription_id: str
    organization_id: str
    plan_version_id: str
    payment_provider: str
    provider_subscription_ref: str
    state: SubscriptionState
    current_period_start: str | None
    current_period_end: str | None
    cancel_at_period_end: bool = False


@dataclass(frozen=True, slots=True)
class CreditLedgerEntry:
    entry_id: str
    organization_id: str
    entry_type: CreditEntryType
    delta_credits: int
    source_type: str
    source_id: str
    pricing_policy_version: int | None
    idempotency_key: str
    created_at: str
    project_id: str | None = None
    usage_record_id: str | None = None
    reverses_entry_id: str | None = None

    def __post_init__(self) -> None:
        if not self.organization_id or not self.idempotency_key:
            raise BillingError("BILLING_CREDIT_IDENTITY_REQUIRED")
        if self.delta_credits == 0:
            raise BillingError("BILLING_CREDIT_DELTA_ZERO")
        if self.entry_type in {"CONSUME", "EXPIRE"} and self.delta_credits >= 0:
            raise BillingError("BILLING_CREDIT_DEBIT_MUST_BE_NEGATIVE")
        if self.entry_type in {"GRANT", "REFUND"} and self.delta_credits <= 0:
            raise BillingError("BILLING_CREDIT_GRANT_MUST_BE_POSITIVE")


@dataclass(frozen=True, slots=True)
class UsagePricingRule:
    usage_key: str
    credits_per_unit: int
    multiplier_basis_points: int = 10_000

    def __post_init__(self) -> None:
        if not self.usage_key.strip() or self.credits_per_unit <= 0 or self.multiplier_basis_points <= 0:
            raise BillingError("BILLING_PRICING_RULE_INVALID")


@dataclass(frozen=True, slots=True)
class PricingPolicyVersion:
    policy_id: str
    version: int
    rules: tuple[UsagePricingRule, ...]
    status: Literal["ACTIVE", "ARCHIVED"] = "ACTIVE"

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or self.version < 1 or not self.rules:
            raise BillingError("BILLING_PRICING_POLICY_INVALID")
        if len({item.usage_key for item in self.rules}) != len(self.rules):
            raise BillingError("BILLING_PRICING_RULE_DUPLICATE")


@dataclass(frozen=True, slots=True)
class BillingUsageRecord:
    usage_record_id: str
    organization_id: str
    project_id: str | None
    usage_key: str
    quantity: str
    unit: str
    credits_consumed: int
    pricing_policy_version: int
    credit_entry_id: str
    provider_cost_entry_ref: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class InvoiceRef:
    invoice_id: str
    organization_id: str
    provider: str
    provider_invoice_ref: str
    plan_version_id: str
    status: Literal["PAID", "OPEN", "FAILED", "VOID"]
    amount_due_microusd: int
    currency: str
    hosted_invoice_url: str | None
    created_at: str

    def __post_init__(self) -> None:
        if not self.plan_version_id.strip() or self.amount_due_microusd < 0:
            raise BillingError("BILLING_INVOICE_VALUE_INVALID")
        if len(self.currency) != 3:
            raise BillingError("BILLING_CURRENCY_INVALID")


@dataclass(frozen=True, slots=True)
class PaymentEvent:
    provider: str
    provider_event_id: str
    organization_id: str
    event_type: PaymentEventType
    payload_hash: str
    received_at: str


@dataclass(frozen=True, slots=True)
class NormalizedPaymentEvent:
    provider: str
    provider_event_id: str
    event_type: PaymentEventType
    organization_id: str
    plan_version_id: str | None = None
    customer_ref: str | None = None
    subscription_ref: str | None = None
    subscription_state: SubscriptionState | None = None
    period_start: str | None = None
    period_end: str | None = None
    invoice_ref: str | None = None
    amount_due_microusd: int | None = None
    currency: str | None = None
    hosted_invoice_url: str | None = None


@dataclass(frozen=True, slots=True)
class HostedSession:
    provider: str
    session_ref: str
    url: str


@dataclass(frozen=True, slots=True)
class ProviderSubscription:
    provider_subscription_ref: str
    state: SubscriptionState
    cancel_at_period_end: bool
    current_period_start: str | None
    current_period_end: str | None


@dataclass(frozen=True, slots=True)
class PaymentProcessResult:
    provider_event_id: str
    disposition: Literal["PROCESSED", "DUPLICATE"]


@dataclass(frozen=True, slots=True)
class BillingSummary:
    organization_id: str
    current_plan: PlanVersion | None
    subscription: Subscription | None
    plans: tuple[PlanVersion, ...]
    credit_balance: int
    credit_entries: tuple[CreditLedgerEntry, ...]
    invoices: tuple[InvoiceRef, ...]
    entitlements: dict[str, int | bool | str]
    can_manage: bool
    payment_provider: str
    provider_cost_reconciliation_available: bool


@dataclass(frozen=True, slots=True)
class RevenueCostReconciliation:
    available: bool
    provider_cost_microusd: int | None
    paid_invoice_revenue_microusd: int
    gross_margin_microusd: int | None


class BillingRepository(Protocol):
    def save_plan_version(self, plan: PlanVersion) -> None: ...
    def get_plan_version(self, plan_version_id: str) -> PlanVersion | None: ...
    def list_plan_versions(self) -> tuple[PlanVersion, ...]: ...
    def save_pricing_policy(self, policy: PricingPolicyVersion) -> None: ...
    def get_pricing_policy(self, version: int) -> PricingPolicyVersion | None: ...
    def get_account(self, organization_id: str) -> BillingAccount | None: ...
    def save_account(self, account: BillingAccount) -> None: ...
    def get_subscription(self, organization_id: str) -> Subscription | None: ...
    def save_subscription(self, subscription: Subscription) -> None: ...
    def append_credit(
        self, entry: CreditLedgerEntry, *, require_non_negative: bool = False
    ) -> CreditLedgerEntry: ...
    def append_refund(
        self, entry: CreditLedgerEntry, *, original_entry_id: str
    ) -> CreditLedgerEntry: ...
    def credit_balance(self, organization_id: str) -> int: ...
    def list_credit_entries(self, organization_id: str) -> tuple[CreditLedgerEntry, ...]: ...
    def save_usage(self, usage: BillingUsageRecord) -> None: ...
    def list_usage(self, organization_id: str) -> tuple[BillingUsageRecord, ...]: ...
    def save_invoice(self, invoice: InvoiceRef) -> None: ...
    def list_invoices(self, organization_id: str) -> tuple[InvoiceRef, ...]: ...
    def run_payment_event_once(self, event: PaymentEvent, apply: Callable[[], None]) -> bool: ...


class PaymentProviderPort(Protocol):
    name: str
    def create_customer(self, organization_id: str, billing_email: str | None) -> str: ...
    def create_checkout(self, customer_ref: str, plan: PlanVersion) -> HostedSession: ...
    def create_portal_session(self, customer_ref: str) -> HostedSession: ...
    def get_subscription(self, provider_subscription_ref: str) -> ProviderSubscription: ...
    def cancel_subscription(self, provider_subscription_ref: str) -> ProviderSubscription: ...
    def verify_webhook(
        self, raw_body: bytes, signature: str
    ) -> tuple[NormalizedPaymentEvent, str]: ...


class ProviderCostPort(Protocol):
    def actual_cost_microusd(self, organization_id: str) -> int | None: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


class BillingEngine:
    def __init__(
        self,
        *,
        repository: BillingRepository,
        payment_provider: PaymentProviderPort,
        provider_costs: ProviderCostPort,
    ) -> None:
        self._repository = repository
        self._provider = payment_provider
        self._provider_costs = provider_costs

    @property
    def payment_provider_name(self) -> str:
        return self._provider.name

    def publish_plan_version(self, actor: BillingActor, plan: PlanVersion) -> PlanVersion:
        self._require(actor, "billing.manage")
        if self._repository.get_plan_version(plan.plan_version_id) is not None:
            raise BillingError("BILLING_PLAN_VERSION_IMMUTABLE", 409)
        self._repository.save_plan_version(plan)
        return plan

    def publish_pricing_policy(
        self, actor: BillingActor, policy: PricingPolicyVersion
    ) -> PricingPolicyVersion:
        self._require(actor, "billing.manage")
        if self._repository.get_pricing_policy(policy.version) is not None:
            raise BillingError("BILLING_PRICING_POLICY_IMMUTABLE", 409)
        self._repository.save_pricing_policy(policy)
        return policy

    def summary(self, actor: BillingActor) -> BillingSummary:
        self._require(actor, "billing.read")
        subscription = self._repository.get_subscription(actor.organization_id)
        current_plan = self._repository.get_plan_version(subscription.plan_version_id) if subscription else None
        return BillingSummary(
            organization_id=actor.organization_id,
            current_plan=current_plan,
            subscription=subscription,
            plans=tuple(
                item for item in self._repository.list_plan_versions() if item.status == "ACTIVE"
            ),
            credit_balance=self._repository.credit_balance(actor.organization_id),
            credit_entries=self._repository.list_credit_entries(actor.organization_id)[:20],
            invoices=self._repository.list_invoices(actor.organization_id)[:20],
            entitlements=self._entitlements(subscription, current_plan),
            can_manage="billing.manage" in actor.permissions,
            payment_provider=self._provider.name,
            provider_cost_reconciliation_available=(
                self._provider_costs.actual_cost_microusd(actor.organization_id) is not None
            ),
        )

    def entitlement(self, actor: BillingActor, key: str) -> int | bool | str | None:
        self._require(actor, "billing.read")
        subscription = self._repository.get_subscription(actor.organization_id)
        plan = self._repository.get_plan_version(subscription.plan_version_id) if subscription else None
        return self._entitlements(subscription, plan).get(key)

    def quote_usage(
        self, actor: BillingActor, pricing_policy_version: int, usage_key: str, quantity: Decimal
    ) -> int:
        self._require(actor, "billing.read")
        if not quantity.is_finite() or quantity <= 0:
            raise BillingError("BILLING_USAGE_QUANTITY_INVALID")
        policy = self._repository.get_pricing_policy(pricing_policy_version)
        if policy is None:
            raise BillingError("BILLING_PRICING_POLICY_NOT_FOUND", 404)
        rule = next((item for item in policy.rules if item.usage_key == usage_key), None)
        if rule is None:
            raise BillingError("BILLING_USAGE_RULE_NOT_FOUND", 404)
        raw = (
            quantity
            * Decimal(rule.credits_per_unit)
            * Decimal(rule.multiplier_basis_points)
            / Decimal(10_000)
        )
        return int(raw.to_integral_value(rounding=ROUND_CEILING))

    def consume_usage(
        self,
        actor: BillingActor,
        *,
        project_id: str | None,
        pricing_policy_version: int,
        usage_key: str,
        quantity: Decimal,
        unit: str,
        usage_record_id: str,
        idempotency_key: str,
        provider_cost_entry_ref: str | None = None,
    ) -> BillingUsageRecord:
        credits = self.quote_usage(actor, pricing_policy_version, usage_key, quantity)
        entry = CreditLedgerEntry(
            entry_id=str(uuid4()),
            organization_id=actor.organization_id,
            project_id=project_id,
            entry_type="CONSUME",
            delta_credits=-credits,
            source_type="USAGE",
            source_id=usage_record_id,
            usage_record_id=usage_record_id,
            pricing_policy_version=pricing_policy_version,
            idempotency_key=idempotency_key,
            created_at=_now(),
        )
        stored = self._repository.append_credit(entry, require_non_negative=True)
        if stored.usage_record_id != usage_record_id:
            raise BillingError("BILLING_IDEMPOTENCY_KEY_REUSED", 409)
        usage = BillingUsageRecord(
            usage_record_id=usage_record_id,
            organization_id=actor.organization_id,
            project_id=project_id,
            usage_key=usage_key,
            quantity=str(quantity),
            unit=unit,
            credits_consumed=abs(stored.delta_credits),
            pricing_policy_version=pricing_policy_version,
            credit_entry_id=stored.entry_id,
            provider_cost_entry_ref=provider_cost_entry_ref,
            created_at=_now(),
        )
        self._repository.save_usage(usage)
        return usage

    def refund_credits(
        self,
        actor: BillingActor,
        *,
        original_entry_id: str,
        credits: int,
        idempotency_key: str,
        reason: str,
    ) -> CreditLedgerEntry:
        self._require(actor, "billing.manage")
        if credits <= 0 or not reason.strip():
            raise BillingError("BILLING_REFUND_INVALID")
        return self._repository.append_refund(
            CreditLedgerEntry(
                entry_id=str(uuid4()),
                organization_id=actor.organization_id,
                entry_type="REFUND",
                delta_credits=credits,
                source_type="REFUND",
                source_id=original_entry_id,
                reverses_entry_id=original_entry_id,
                pricing_policy_version=None,
                idempotency_key=idempotency_key,
                created_at=_now(),
            ),
            original_entry_id=original_entry_id,
        )

    def create_checkout(self, actor: BillingActor, plan_version_id: str) -> HostedSession:
        self._require(actor, "billing.manage")
        plan = self._repository.get_plan_version(plan_version_id)
        if plan is None or plan.status != "ACTIVE":
            raise BillingError("BILLING_PLAN_VERSION_NOT_AVAILABLE", 404)
        account = self._repository.get_account(actor.organization_id)
        if account is None:
            account = BillingAccount(
                organization_id=actor.organization_id,
                payment_provider=self._provider.name,
                payment_customer_ref=self._provider.create_customer(
                    actor.organization_id, actor.billing_email
                ),
                created_at=_now(),
            )
            self._repository.save_account(account)
        if account.payment_provider != self._provider.name:
            raise BillingError("BILLING_PAYMENT_PROVIDER_MISMATCH", 409)
        return self._provider.create_checkout(account.payment_customer_ref, plan)

    def create_portal(self, actor: BillingActor) -> HostedSession:
        self._require(actor, "billing.manage")
        account = self._repository.get_account(actor.organization_id)
        if account is None:
            raise BillingError("BILLING_PAYMENT_CUSTOMER_NOT_FOUND", 404)
        if account.payment_provider != self._provider.name:
            raise BillingError("BILLING_PAYMENT_PROVIDER_MISMATCH", 409)
        return self._provider.create_portal_session(account.payment_customer_ref)

    def cancel_subscription(self, actor: BillingActor) -> Subscription:
        self._require(actor, "billing.manage")
        current = self._repository.get_subscription(actor.organization_id)
        if current is None:
            raise BillingError("BILLING_SUBSCRIPTION_NOT_FOUND", 404)
        if current.payment_provider != self._provider.name:
            raise BillingError("BILLING_PAYMENT_PROVIDER_MISMATCH", 409)
        provider_state = self._provider.cancel_subscription(current.provider_subscription_ref)
        updated = replace(
            current,
            state=provider_state.state,
            cancel_at_period_end=provider_state.cancel_at_period_end,
            current_period_start=provider_state.current_period_start,
            current_period_end=provider_state.current_period_end,
        )
        self._repository.save_subscription(updated)
        return updated

    def process_webhook(self, raw_body: bytes, signature: str) -> PaymentProcessResult:
        normalized, payload_hash = self._provider.verify_webhook(raw_body, signature)
        event = PaymentEvent(
            provider=normalized.provider,
            provider_event_id=normalized.provider_event_id,
            organization_id=normalized.organization_id,
            event_type=normalized.event_type,
            payload_hash=payload_hash,
            received_at=_now(),
        )
        processed = self._repository.run_payment_event_once(
            event, lambda: self._apply_payment_event(normalized)
        )
        return PaymentProcessResult(
            provider_event_id=normalized.provider_event_id,
            disposition="PROCESSED" if processed else "DUPLICATE",
        )

    def reconciliation(self, actor: BillingActor) -> RevenueCostReconciliation:
        self._require(actor, "billing.manage")
        provider_cost = self._provider_costs.actual_cost_microusd(actor.organization_id)
        revenue = sum(
            item.amount_due_microusd
            for item in self._repository.list_invoices(actor.organization_id)
            if item.status == "PAID"
        )
        return RevenueCostReconciliation(
            available=provider_cost is not None,
            provider_cost_microusd=provider_cost,
            paid_invoice_revenue_microusd=revenue,
            gross_margin_microusd=None if provider_cost is None else revenue - provider_cost,
        )

    def _apply_payment_event(self, event: NormalizedPaymentEvent) -> None:
        if event.event_type in {
            "SUBSCRIPTION_CREATED",
            "SUBSCRIPTION_UPDATED",
            "SUBSCRIPTION_CANCELLED",
        }:
            if not event.subscription_ref or not event.plan_version_id or not event.subscription_state:
                raise BillingError("BILLING_WEBHOOK_SUBSCRIPTION_INCOMPLETE")
            if self._repository.get_plan_version(event.plan_version_id) is None:
                raise BillingError("BILLING_WEBHOOK_PLAN_VERSION_UNKNOWN", 409)
            self._repository.save_subscription(
                Subscription(
                    subscription_id=f"sub-{event.organization_id}",
                    organization_id=event.organization_id,
                    plan_version_id=event.plan_version_id,
                    payment_provider=event.provider,
                    provider_subscription_ref=event.subscription_ref,
                    state=event.subscription_state,
                    current_period_start=event.period_start,
                    current_period_end=event.period_end,
                    cancel_at_period_end=event.subscription_state == "CANCEL_AT_PERIOD_END",
                )
            )
            return

        if (
            not event.invoice_ref
            or not event.plan_version_id
            or event.amount_due_microusd is None
            or not event.currency
        ):
            raise BillingError("BILLING_WEBHOOK_INVOICE_INCOMPLETE")
        plan = self._repository.get_plan_version(event.plan_version_id)
        if plan is None:
            raise BillingError("BILLING_WEBHOOK_PLAN_VERSION_UNKNOWN", 409)
        status: Literal["PAID", "FAILED"] = (
            "PAID" if event.event_type == "INVOICE_PAID" else "FAILED"
        )
        self._repository.save_invoice(
            InvoiceRef(
                invoice_id=f"invoice-{event.provider}-{event.invoice_ref}",
                organization_id=event.organization_id,
                provider=event.provider,
                provider_invoice_ref=event.invoice_ref,
                plan_version_id=event.plan_version_id,
                status=status,
                amount_due_microusd=event.amount_due_microusd,
                currency=event.currency,
                hosted_invoice_url=event.hosted_invoice_url,
                created_at=_now(),
            )
        )
        if event.event_type == "INVOICE_PAID" and plan.monthly_credit_grant > 0:
            self._repository.append_credit(
                CreditLedgerEntry(
                    entry_id=str(uuid4()),
                    organization_id=event.organization_id,
                    entry_type="GRANT",
                    delta_credits=plan.monthly_credit_grant,
                    source_type="INVOICE",
                    source_id=event.invoice_ref,
                    pricing_policy_version=None,
                    idempotency_key=(
                        f"invoice:{event.provider}:{event.invoice_ref}:"
                        f"{event.plan_version_id}:credit-grant"
                    ),
                    created_at=_now(),
                )
            )

    @staticmethod
    def _entitlements(
        subscription: Subscription | None, plan: PlanVersion | None
    ) -> dict[str, int | bool | str]:
        if (
            subscription is None
            or plan is None
            or subscription.state not in ACTIVE_ENTITLEMENT_STATES
        ):
            return {}
        return dict(plan.entitlements)

    @staticmethod
    def _require(actor: BillingActor, permission: str) -> None:
        if permission not in actor.permissions:
            raise BillingError("BILLING_FORBIDDEN", 403)


class InMemoryBillingRepository:
    def __init__(self) -> None:
        self.plans: dict[str, PlanVersion] = {}
        self.policies: dict[int, PricingPolicyVersion] = {}
        self.accounts: dict[str, BillingAccount] = {}
        self.subscriptions: dict[str, Subscription] = {}
        self.credits: dict[str, list[CreditLedgerEntry]] = {}
        self.credit_idempotency: dict[tuple[str, str], CreditLedgerEntry] = {}
        self.usage: dict[str, list[BillingUsageRecord]] = {}
        self.invoices: dict[str, list[InvoiceRef]] = {}
        self.payment_events: dict[tuple[str, str], PaymentEvent] = {}
        self._lock = RLock()

    def save_plan_version(self, plan: PlanVersion) -> None:
        if plan.plan_version_id in self.plans:
            raise BillingError("BILLING_PLAN_VERSION_IMMUTABLE", 409)
        self.plans[plan.plan_version_id] = plan

    def get_plan_version(self, plan_version_id: str) -> PlanVersion | None:
        return self.plans.get(plan_version_id)

    def list_plan_versions(self) -> tuple[PlanVersion, ...]:
        return tuple(sorted(self.plans.values(), key=lambda item: (item.name, item.version)))

    def save_pricing_policy(self, policy: PricingPolicyVersion) -> None:
        if policy.version in self.policies:
            raise BillingError("BILLING_PRICING_POLICY_IMMUTABLE", 409)
        self.policies[policy.version] = policy

    def get_pricing_policy(self, version: int) -> PricingPolicyVersion | None:
        return self.policies.get(version)

    def get_account(self, organization_id: str) -> BillingAccount | None:
        return self.accounts.get(organization_id)

    def save_account(self, account: BillingAccount) -> None:
        self.accounts[account.organization_id] = account

    def get_subscription(self, organization_id: str) -> Subscription | None:
        return self.subscriptions.get(organization_id)

    def save_subscription(self, subscription: Subscription) -> None:
        self.subscriptions[subscription.organization_id] = subscription

    def append_credit(
        self, entry: CreditLedgerEntry, *, require_non_negative: bool = False
    ) -> CreditLedgerEntry:
        with self._lock:
            key = (entry.organization_id, entry.idempotency_key)
            prior = self.credit_idempotency.get(key)
            if prior is not None:
                return prior
            balance = sum(
                item.delta_credits for item in self.credits.get(entry.organization_id, [])
            )
            if require_non_negative and balance + entry.delta_credits < 0:
                raise BillingError("BILLING_INSUFFICIENT_CREDITS", 402)
            self.credits.setdefault(entry.organization_id, []).append(entry)
            self.credit_idempotency[key] = entry
            return entry

    def append_refund(
        self, entry: CreditLedgerEntry, *, original_entry_id: str
    ) -> CreditLedgerEntry:
        with self._lock:
            key = (entry.organization_id, entry.idempotency_key)
            prior = self.credit_idempotency.get(key)
            if prior is not None:
                if prior.reverses_entry_id != original_entry_id:
                    raise BillingError("BILLING_IDEMPOTENCY_KEY_REUSED", 409)
                return prior
            values = self.credits.get(entry.organization_id, [])
            original = next(
                (item for item in values if item.entry_id == original_entry_id), None
            )
            if original is None or original.entry_type != "CONSUME":
                raise BillingError("BILLING_REFUND_SOURCE_INVALID", 404)
            refunded = sum(
                item.delta_credits
                for item in values
                if item.entry_type == "REFUND" and item.reverses_entry_id == original_entry_id
            )
            if refunded + entry.delta_credits > abs(original.delta_credits):
                raise BillingError("BILLING_REFUND_EXCEEDS_CONSUME", 409)
            self.credits.setdefault(entry.organization_id, []).append(entry)
            self.credit_idempotency[key] = entry
            return entry

    def credit_balance(self, organization_id: str) -> int:
        with self._lock:
            return sum(item.delta_credits for item in self.credits.get(organization_id, []))

    def list_credit_entries(self, organization_id: str) -> tuple[CreditLedgerEntry, ...]:
        return tuple(reversed(self.credits.get(organization_id, [])))

    def save_usage(self, usage: BillingUsageRecord) -> None:
        values = self.usage.setdefault(usage.organization_id, [])
        prior = next(
            (item for item in values if item.usage_record_id == usage.usage_record_id), None
        )
        if prior is not None and prior.credit_entry_id != usage.credit_entry_id:
            raise BillingError("BILLING_USAGE_ID_REUSED", 409)
        if prior is None:
            values.append(usage)

    def list_usage(self, organization_id: str) -> tuple[BillingUsageRecord, ...]:
        return tuple(self.usage.get(organization_id, []))

    def save_invoice(self, invoice: InvoiceRef) -> None:
        values = self.invoices.setdefault(invoice.organization_id, [])
        prior = next(
            (item for item in values if item.provider_invoice_ref == invoice.provider_invoice_ref),
            None,
        )
        if prior is not None and prior.plan_version_id != invoice.plan_version_id:
            raise BillingError("BILLING_INVOICE_PLAN_VERSION_CONFLICT", 409)
        values[:] = [
            item for item in values if item.provider_invoice_ref != invoice.provider_invoice_ref
        ]
        values.append(invoice)

    def list_invoices(self, organization_id: str) -> tuple[InvoiceRef, ...]:
        return tuple(reversed(self.invoices.get(organization_id, [])))

    def run_payment_event_once(self, event: PaymentEvent, apply: Callable[[], None]) -> bool:
        with self._lock:
            key = (event.provider, event.provider_event_id)
            prior = self.payment_events.get(key)
            if prior is not None:
                if prior.payload_hash != event.payload_hash:
                    raise BillingError("BILLING_WEBHOOK_EVENT_ID_COLLISION", 409)
                return False
            apply()
            self.payment_events[key] = event
            return True


class MockPaymentProvider:
    name = "MOCK"
    signature = "mock-signature-v1"

    def __init__(self) -> None:
        self.subscriptions: dict[str, ProviderSubscription] = {}

    def create_customer(self, organization_id: str, billing_email: str | None) -> str:
        suffix = sha256(f"{organization_id}:{billing_email or ''}".encode()).hexdigest()[:12]
        return f"mock_cus_{suffix}"

    def create_checkout(self, customer_ref: str, plan: PlanVersion) -> HostedSession:
        ref = f"mock_checkout_{uuid4().hex[:12]}"
        return HostedSession(
            self.name,
            ref,
            f"https://checkout.mock.invalid/session/{ref}?plan={plan.plan_version_id}",
        )

    def create_portal_session(self, customer_ref: str) -> HostedSession:
        ref = f"mock_portal_{uuid4().hex[:12]}"
        return HostedSession(self.name, ref, f"https://portal.mock.invalid/session/{ref}")

    def get_subscription(self, provider_subscription_ref: str) -> ProviderSubscription:
        value = self.subscriptions.get(provider_subscription_ref)
        if value is None:
            raise BillingError("BILLING_PROVIDER_SUBSCRIPTION_NOT_FOUND", 404)
        return value

    def cancel_subscription(self, provider_subscription_ref: str) -> ProviderSubscription:
        current = self.subscriptions.get(
            provider_subscription_ref,
            ProviderSubscription(provider_subscription_ref, "ACTIVE", False, None, None),
        )
        updated = replace(current, state="CANCEL_AT_PERIOD_END", cancel_at_period_end=True)
        self.subscriptions[provider_subscription_ref] = updated
        return updated

    def verify_webhook(
        self, raw_body: bytes, signature: str
    ) -> tuple[NormalizedPaymentEvent, str]:
        if signature != self.signature:
            raise BillingError("BILLING_WEBHOOK_SIGNATURE_INVALID", 401)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BillingError("BILLING_WEBHOOK_INVALID") from error
        if not isinstance(body, dict):
            raise BillingError("BILLING_WEBHOOK_INVALID")
        event_id = _string(body.get("id"))
        event_type = _string(body.get("type"))
        organization_id = _string(body.get("organization_id"))
        if not event_id or not event_type or not organization_id:
            raise BillingError("BILLING_WEBHOOK_INVALID")
        if event_type not in VALID_PAYMENT_EVENT_TYPES:
            raise BillingError("BILLING_WEBHOOK_EVENT_UNSUPPORTED")
        state = _string(body.get("subscription_state"))
        if state is not None and state not in VALID_SUBSCRIPTION_STATES:
            raise BillingError("BILLING_WEBHOOK_SUBSCRIPTION_STATE_INVALID")
        return (
            NormalizedPaymentEvent(
                provider=self.name,
                provider_event_id=event_id,
                event_type=event_type,  # type: ignore[arg-type]
                organization_id=organization_id,
                plan_version_id=_string(body.get("plan_version_id")),
                customer_ref=_string(body.get("customer_ref")),
                subscription_ref=_string(body.get("subscription_ref")),
                subscription_state=state,  # type: ignore[arg-type]
                period_start=_string(body.get("period_start")),
                period_end=_string(body.get("period_end")),
                invoice_ref=_string(body.get("invoice_ref")),
                amount_due_microusd=_integer(body.get("amount_due_microusd")),
                currency=_string(body.get("currency")),
                hosted_invoice_url=_https_url(body.get("hosted_invoice_url")),
            ),
            sha256(raw_body).hexdigest(),
        )


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _https_url(value: Any) -> str | None:
    candidate = _string(value)
    if candidate is None:
        return None
    return candidate if candidate.startswith("https://") else None


class StaticProviderCostPort:
    def __init__(self, costs: dict[str, int | None] | None = None) -> None:
        self.costs = costs or {}

    def actual_cost_microusd(self, organization_id: str) -> int | None:
        return self.costs.get(organization_id)
