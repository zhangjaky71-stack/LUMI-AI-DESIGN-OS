# NODE-63 — Billing, Plans, Credits & Payment Integration

> Phase: 8 SaaS & Collaboration  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P1 / COMMERCIALIZATION  
> Depends on: NODE-16, NODE-27, NODE-20  
> Produces: PlanVersion/Entitlement、immutable Credits、Subscription、Mock Payment Provider、webhook idempotency、Billing UX

## 1. Goal

Commercialize LUMI without mixing provider costs, customer usage, customer charges and product entitlements. NODE-63 implements the customer-side billing domain while treating NODE-27 Provider Cost Ledger as a separate read-only integration port.

## 2. Canonical truth separation

```text
Provider Cost Ledger  != Customer Usage
Customer Usage        != Customer Billing
Customer Billing      != Credits / Entitlements
```

NODE-63 never rewrites or fabricates NODE-27 provider-cost truth.

## 3. Product surface

`/app/billing` replaces the App Shell placeholder with:

- exact current PlanVersion and normalized Subscription state;
- immutable Credit Ledger balance/entries;
- included-credit usage projection;
- entitlement projection;
- available PlanVersions;
- Hosted Checkout / Hosted Payment Portal actions;
- cancel-at-period-end;
- invoice references with exact PlanVersion;
- explicit provider-cost reconciliation availability;
- responsive mobile layout.

The browser never collects raw payment-instrument credentials. Hosted billing and invoice URLs are rendered only when HTTPS.

## 4. Domain

Implemented in `lumi_project_core.billing`:

- `PlanVersion`;
- `BillingAccount`;
- `Subscription`;
- `CreditLedgerEntry`;
- `PricingPolicyVersion` / `UsagePricingRule`;
- `BillingUsageRecord`;
- `InvoiceRef`;
- `PaymentEvent` / `NormalizedPaymentEvent`;
- `PaymentProviderPort` and `MockPaymentProvider`;
- `ProviderCostPort`;
- `BillingEngine`.

## 5. Exact PlanVersion semantics

Plan versions are immutable. Existing subscriptions retain exact `plan_version_id`; publishing v3 changes neither price nor entitlement policy for a subscription pinned to v2 until an explicit migration occurs.

Every invoice also stores exact `plan_version_id`. A delayed v2 invoice received after the subscription has moved to v3 must grant the v2 credit amount, not whatever the current subscription happens to contain.

This prevents asynchronous payment delivery from silently changing commercial semantics.

## 6. Entitlements

Feature code queries Billing/Entitlement service keys such as:

```text
video_enabled
max_concurrent_generations
team_seats
brand_kits
priority_routing
```

No `if plan == "pro"` policy is introduced.

P0 entitlement-bearing states are:

```text
TRIALING
ACTIVE
CANCEL_AT_PERIOD_END
```

`PAST_DUE`, `CANCELLED`, and `INCOMPLETE` fail closed unless a future explicit grace/postpaid policy says otherwise.

## 7. Immutable Credit Ledger

Ledger types:

```text
GRANT
CONSUME
REFUND
EXPIRE
ADJUSTMENT
REVERSAL
```

Balance is a rebuildable projection from immutable rows.

Two correctness boundaries are explicit:

1. `append_credit(... require_non_negative=True)` atomically blocks consumption that would make the balance negative;
2. `append_refund(...)` atomically validates the original CONSUME, prior refund total, and new REFUND append so concurrent refunds cannot exceed the original debit.

Refunds never mutate or delete the original CONSUME.

## 8. Versioned usage conversion

Credits are not provider dollars. `PricingPolicyVersion` maps Decimal/numeric usage quantities to integer credits using versioned rules and basis-point multipliers.

Every `BillingUsageRecord` retains:

```text
usage_record_id
usage_key / quantity / unit
credits_consumed
pricing_policy_version
credit_entry_id
provider_cost_entry_ref?
```

The optional provider-cost reference is only an opaque reconciliation link to NODE-27. Reusing one usage idempotency key for a different usage record fails closed.

## 9. Payment Provider boundary

P0 implements `MockPaymentProvider` for deterministic engineering and tests:

```text
create_customer
create_checkout
create_portal_session
get_subscription
cancel_subscription
verify_webhook
```

Checkout and payment-method management stay on Hosted Payment Provider pages. LUMI stores provider customer/subscription/invoice references, not raw payment credentials.

A real provider sandbox remains a production integration gate because merchant onboarding and secret provisioning cannot be fabricated by repository code.

## 10. Webhook correctness

Canonical webhook path:

```text
verify signature
→ normalize + validate provider state
→ hash raw payload
→ idempotency by (provider, provider_event_id)
→ reject same event id with different payload hash
→ transactional subscription / invoice / credit effect
→ mark processed
```

Duplicate delivery cannot double-grant credits. `INVOICE_PAID` additionally uses an immutable ledger idempotency key containing provider, invoice reference and exact PlanVersion.

Normalized subscription states:

```text
TRIALING
ACTIVE
PAST_DUE
CANCEL_AT_PERIOD_END
CANCELLED
INCOMPLETE
```

Provider-specific unknown states do not leak into the domain; the adapter must normalize or fail closed.

## 11. No negative surprise

Paid generation/tool/model paths must quote and atomically consume credits before invoking an expensive provider. Insufficient balance returns `BILLING_INSUFFICIENT_CREDITS` before the paid operation starts.

Negative balances are not an implicit feature. Enterprise postpaid requires a future explicit contract/policy.

## 12. Persistence

`db/migrations/0013_billing.sql` adds:

- `billing_plan_versions`;
- `billing_pricing_policies`;
- `billing_accounts`;
- `billing_subscriptions`;
- `billing_credit_ledger`;
- `billing_usage_records`;
- `billing_invoices`;
- `billing_payment_events`;
- `billing_credit_balances` projection view.

`billing_invoices.plan_version_id` is a foreign key to the immutable PlanVersion. Payment events persist provider event identity, organization, event type and payload hash—not raw card data.

The production repository must implement webhook, consume and refund limits with real database transaction/locking semantics.

## 13. API

```text
GET  /billing
POST /billing/checkout
POST /billing/portal
POST /billing/subscription:cancel
POST /billing/usage:quote
POST /billing/webhooks/{provider}
```

User-facing reads require `billing.read`; customer-management actions require `billing.manage`; provider webhooks use provider signature verification rather than browser-session authorization.

## 14. Provider cost reconciliation

`ProviderCostPort` is read-only. Customer paid-invoice revenue is aggregated independently from provider costs, and gross-margin projection is exposed only when a real NODE-27 runtime adapter exists.

The current repository has the NODE-27 specification but not a completed provider-cost runtime; NODE-63 therefore reports reconciliation unavailable rather than inventing cost values.

## 15. Tests staged

- immutable PlanVersion and pinned Subscription;
- delayed old-plan invoice grants old-plan credits;
- signed webhook / invalid signature / invalid normalized state;
- duplicate webhook no double grant;
- same provider event id + different payload hash collision;
- concurrent credit consumption never negative;
- usage idempotency-key reuse rejection;
- refund preserves old CONSUME;
- concurrent refunds cannot over-refund;
- cancellation entitlement transition;
- Hosted Checkout/Portal without local payment form;
- provider cost vs customer revenue separation;
- API permission/hosted session/webhook tests;
- PostgreSQL schema/projection tests;
- frontend contract/gateway tests and HTTPS-link guard;
- browser Billing UX/mobile;
- prior-node regressions.

## 16. Production integration gates

1. durable PostgreSQL `BillingRepository` with transaction/locking semantics;
2. deployed NODE-16 actor resolver for `billing.read` / `billing.manage`;
3. NODE-27 real Provider Cost Ledger runtime + reconciliation adapter;
4. paid generation/model/tool paths consume credits before provider invocation;
5. versioned generation-failure refund policy integration;
6. real Payment Provider sandbox + merchant account + secret configuration;
7. webhook retry/reconciliation operations and provider-specific replay policy;
8. if YEAR plans are enabled, explicit monthly-credit scheduler/policy rather than assuming annual invoice cadence equals credit cadence;
9. jurisdiction-specific tax/invoice configuration reviewed by finance/legal;
10. hosted pinned CI observed green.

## 17. Acceptance

- [x] Mock payment engineering flow implemented;
- [x] webhook signature/idempotency/hash collision contract;
- [x] immutable Credit Ledger;
- [x] atomic non-negative consumption;
- [x] atomic refund-limit contract;
- [x] exact invoice PlanVersion semantics;
- [x] entitlement service by key, not plan-name branches;
- [x] hosted payment boundary; raw payment credentials excluded;
- [x] provider cost/customer revenue reconciliation port;
- [x] Billing UX implemented;
- [x] validation staged;
- [ ] production adapters connected;
- [ ] real payment sandbox accepted;
- [ ] hosted pinned gates green.

## 18. Definition of Done

```text
billing domain + mock provider implemented
+ webhook/idempotency/credit/refund tests observed green
+ production transaction adapters connected
+ real provider only after sandbox acceptance
```

Next: **NODE-64 — Admin Console**.
