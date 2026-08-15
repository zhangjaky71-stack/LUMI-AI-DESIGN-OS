# Billing Runtime V1

## Truth separation

```text
NODE-27 Provider Cost Ledger  -> what LUMI pays providers
NODE-63 Customer Usage        -> product units consumed
NODE-63 Credit Ledger         -> product usage rights
NODE-63 Customer Billing      -> subscription/invoice/payment references
```

These are separate ledgers/projections. Provider cost is never overwritten by credits or customer revenue.

## Hosted payment boundary

LUMI business APIs never accept raw payment-instrument credentials. Checkout/payment-method management is delegated to a compliant hosted Payment Provider page. LUMI stores only provider customer/subscription/invoice references and normalized status. Browser billing links are also restricted to HTTPS before rendering.

P0 ships `MockPaymentProvider`, which supports customer creation, hosted checkout, hosted portal, subscription cancellation, signed webhook verification and deterministic sandbox events. A real provider is an integration gate after sandbox acceptance and merchant onboarding.

## Plan and invoice versioning

Plan pricing/rights are immutable `PlanVersion` records. A subscription pins an exact `plan_version_id`; publishing v3 never silently reprices a subscription pinned to v2. Every invoice reference also pins exact `plan_version_id`. A delayed v2 invoice that arrives after a subscription moved to v3 grants credits from v2, never from the current subscription head.

Product code queries entitlements through Billing/Entitlement service rather than testing plan names.

## Credits

`billing_credit_ledger` is append-only. Balance is `SUM(delta_credits)` and can be rebuilt. Entry types: GRANT, CONSUME, REFUND, EXPIRE, ADJUSTMENT, REVERSAL. Production consumption must serialize/lock per organization and reject a CONSUME if the resulting balance would be negative. Refund validation and append are also one repository transaction boundary, so concurrent refunds cannot exceed the original CONSUME. Failed generation refunds append REFUND/REVERSAL; old CONSUME entries remain untouched.

## Usage pricing

`PricingPolicyVersion` converts product usage to credits and is independent from provider cost. Rules use integer credits plus basis-point multipliers; quantity uses Decimal/numeric. Each usage record stores the policy version and may carry an opaque NODE-27 provider cost entry reference for later margin reconciliation. Usage idempotency keys cannot be reused for another usage record.

## Webhook correctness

```text
verify provider signature
-> normalize provider event + validate normalized state
-> hash raw payload (do not persist payment instrument data)
-> idempotency by (provider, provider_event_id)
-> reject same event id with a different payload hash
-> transactional subscription/invoice/credit effect
-> mark processed
```

`BillingRepository.run_payment_event_once` is the P0 transaction boundary. The production PostgreSQL adapter must implement the event claim + financial effects in one database transaction (or equivalent durable inbox/outbox protocol). A duplicate invoice webhook must never grant monthly credits twice.

## No negative surprise

Paid operations call quote/consume before provider execution. Atomic credit consumption fails with `BILLING_INSUFFICIENT_CREDITS` before the expensive task starts. Enterprise postpaid is a future explicit contract, not an implicit negative balance.

## Provider Cost reconciliation

`ProviderCostPort` reads NODE-27 actual provider costs without mutating them. Customer paid invoice revenue remains separate. Margin projection is available only when the NODE-27 runtime adapter exists; until then the UI says reconciliation is pending instead of inventing cost data.

## Production integration gates

1. Durable PostgreSQL BillingRepository with transaction/locking semantics for webhooks, credit consumption and refund limits.
2. NODE-16 trusted `billing.read` / `billing.manage` actor resolver in deployed API.
3. NODE-27 Provider Cost Ledger runtime + reconciliation adapter.
4. Model/generation/tool paths call quote + consume before paid execution and append refunds according to versioned policy.
5. Real Payment Provider sandbox adapter after merchant account/API key provisioning; production secrets live in secret management.
6. Provider-specific signed webhook endpoint, replay tolerance and event retry/reconciliation jobs.
7. If YEAR billing plans are enabled, deploy an explicit monthly-credit grant scheduler/policy rather than assuming annual invoice cadence equals monthly entitlement cadence.
8. Tax/invoice configuration verified with finance/legal for target jurisdictions; no hard-coded tax rates in LUMI.

Until these are connected and hosted gates execute green, NODE-63 remains IMPLEMENTED / VALIDATING / NOT COMPLETE.
