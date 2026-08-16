# Stripe Live Purchase Drill

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This runbook defines the production evidence required to clear the NODE-73 Stripe live-purchase gate. Unit tests, test-mode Checkout, mocked webhooks, or PostgreSQL integration tests do **not** satisfy this gate.

## Safety boundary

The drill intentionally requires an operator-approved real payment method and a reviewed low-value live recurring Price. Source automation must never invent card details, expose payment credentials in logs, or initiate a real charge without explicit payment authorization.

Never store any of the following in Git, workflow artifacts, screenshots, or acceptance JSON:

- Stripe secret keys;
- webhook signing secrets;
- card numbers, CVC, bank credentials, or wallet tokens;
- full Checkout Session URLs;
- session cookies or CSRF tokens.

Stripe object IDs such as `price_`, `cus_`, `cs_`, `sub_`, `in_`, and `evt_` may be recorded as non-secret correlation identifiers, subject to the organization's normal evidence-retention policy.

## Production prerequisites

All items below are mandatory before the first live Checkout is created:

1. The exact release candidate SHA is deployed to production.
2. Migration `0019_stripe_billing_runtime` is applied.
3. The production API starts successfully with `LUMI_ENV=production`.
4. `billing/stripe-secret-key` contains the approved `sk_live_...` credential.
5. `billing/stripe-webhook-secret` contains the signing secret for the production endpoint only.
6. The Stripe webhook/event destination is exactly:
   `https://<production-domain>/api/v1/billing/webhooks/stripe`.
7. The webhook endpoint is pinned to API version `2026-02-25.clover`.
8. At minimum, the destination delivers:
   - `customer.subscription.created`;
   - `customer.subscription.updated`;
   - `customer.subscription.deleted`;
   - `invoice.paid`;
   - `invoice.payment_failed`.
9. `stripe_plan_catalog_json` references a reviewed **live** Stripe Price for every active production plan.
10. Startup Price reconciliation has passed. For each plan, LUMI must have verified:
    - Price is active;
    - `livemode=true`;
    - `type=recurring`;
    - `billing_scheme=per_unit`;
    - currency is USD;
    - Stripe `unit_amount` equals the immutable LUMI `price_microusd` value;
    - recurring interval and interval count match the LUMI plan;
    - usage type is `licensed`.
11. `LUMI_ALLOWED_ORIGINS` contains only the intended production browser origin(s).
12. The acceptance organization is disposable or explicitly approved for this drill and has an OWNER or BILLING actor.
13. Finance/product approval identifies the exact live Price ID and maximum charge permitted for the drill.

If any prerequisite is missing, record **BLOCKED_EXTERNAL** or **VALIDATION_PENDING** as appropriate. Do not substitute test mode.

## Phase 1 — freeze drill identity

Record the following before Checkout creation:

- UTC start timestamp;
- release candidate Git SHA;
- production deployment/task-definition identifiers;
- acceptance organization UUID;
- LUMI plan version ID;
- approved Stripe live Price ID;
- approved maximum charge;
- operator identity and approval reference.

Do not record secrets.

## Phase 2 — create authenticated Checkout

Use either:

- a production browser session for an OWNER/BILLING actor with a valid CSRF token and allowed `Origin`; or
- an API token explicitly scoped with `billing.manage`.

Call:

```text
POST /api/v1/billing/checkout
Idempotency-Key: <fresh random 8-128 character key>
Content-Type: application/json

{"plan_version_id":"<approved-plan-version>"}
```

Required observations:

- response provider is `STRIPE`;
- response contains a Stripe Checkout Session reference;
- the browser is redirected only to Stripe-hosted Checkout;
- no client-supplied amount, currency, or Stripe Price ID is accepted by the LUMI API.

### Retry proof

Before completing payment, repeat the same API request with the **same** `Idempotency-Key`.

Required result:

- the retry resolves to the same Stripe Checkout operation/session rather than creating a second payable session.

Then use a different `Idempotency-Key` only if intentionally starting a distinct Checkout attempt.

## Phase 3 — complete one approved real payment

Complete the Stripe-hosted Checkout with the operator-approved real payment method.

Required Stripe-side evidence:

- Checkout Session ID (`cs_...`);
- Customer ID (`cus_...`);
- Subscription ID (`sub_...`);
- Invoice ID (`in_...`);
- `customer.subscription.created` Event ID (`evt_...`);
- `invoice.paid` Event ID (`evt_...`);
- charged amount and currency;
- `livemode=true`;
- event API version `2026-02-25.clover`.

Do not capture payment-method secrets.

## Phase 4 — verify LUMI durable state

Run `scripts/verify_stripe_live_purchase_db.py` from an approved production diagnostic context using the normal application DB role and the exact correlation IDs from Phase 3.

The verifier must report all of the following:

- one STRIPE billing account for the organization;
- the expected subscription reference is `ACTIVE` on the expected immutable plan version;
- the expected invoice reference is `PAID`;
- invoice currency is `USD`;
- invoice `amount_due_microusd` exactly equals the immutable plan price;
- the exact subscription-created and invoice-paid Event IDs exist once;
- the invoice produced exactly one credit `GRANT` entry;
- granted credits exactly equal the plan's monthly credit grant;
- the plan entitlements are therefore eligible to become active through the Billing summary.

Also call `GET /api/v1/billing` as the acceptance actor and archive the non-secret response showing:

- current plan version;
- subscription state `ACTIVE`;
- expected entitlements;
- expected invoice reference/status;
- credit balance including the single invoice grant.

## Phase 5 — webhook replay/idempotency proof

From Stripe Workbench/Dashboard, resend the exact `invoice.paid` event captured in Phase 3 to the same production webhook endpoint.

Required evidence:

1. Stripe records a successful delivery response.
2. LUMI logs/trace show the event was recognized as a replay (`DUPLICATE`).
3. Re-run `scripts/verify_stripe_live_purchase_db.py`.
4. `billing_payment_events` still has one row for that exact `(STRIPE, event_id)` identity.
5. `billing_credit_ledger` still has exactly one invoice grant for that invoice and plan.
6. Credit balance has not increased a second time.

A replay that creates a second credit grant is an automatic **FAIL**.

## Phase 6 — Billing Portal and cancellation lifecycle

Create a Billing Portal session through:

```text
POST /api/v1/billing/portal
```

For cookie authentication, CSRF and allowed Origin protections must still be enforced.

Use the Portal or the LUMI cancellation endpoint to set cancellation at period end. Verify the resulting signed Stripe subscription webhook updates LUMI to `CANCEL_AT_PERIOD_END` without removing entitlements before the paid period ends.

Do not wait for the actual billing period to expire solely for Final Acceptance unless product policy explicitly requires expiry proof. The live purchase gate focuses on charge, durable webhook state, replay safety, and cancellation scheduling.

## Required evidence manifest

Store a redacted manifest in the release evidence location with at least:

```json
{
  "status": "PASS|FAIL|BLOCKED_EXTERNAL",
  "environment": "production",
  "release_sha": "<git-sha>",
  "started_at_utc": "<timestamp>",
  "completed_at_utc": "<timestamp>",
  "organization_id": "<uuid>",
  "plan_version_id": "<plan-version>",
  "stripe_price_id": "price_...",
  "stripe_checkout_session_id": "cs_...",
  "stripe_customer_id": "cus_...",
  "stripe_subscription_id": "sub_...",
  "stripe_invoice_id": "in_...",
  "stripe_subscription_event_id": "evt_...",
  "stripe_invoice_event_id": "evt_...",
  "charged_currency": "USD",
  "charged_amount_microusd": 0,
  "subscription_state_after_purchase": "ACTIVE",
  "invoice_state": "PAID",
  "credit_grant_count": 1,
  "webhook_replay_disposition": "DUPLICATE",
  "credit_grant_count_after_replay": 1,
  "billing_summary_verified": true,
  "operator": "<approved-identity>",
  "approval_reference": "<ticket/change-reference>"
}
```

Never place a Checkout URL, Stripe secret, webhook secret, card data, cookie, CSRF token, or Authorization header in this manifest.

## PASS criteria

The Stripe live-purchase gate is **PASS** only when all of these are true for the exact release candidate:

- production live-mode source configuration is deployed and healthy;
- startup Price reconciliation passes against the exact live Price;
- authenticated Checkout succeeds with a server-owned Price;
- a real approved payment succeeds exactly once;
- signed live-mode webhooks reach the production endpoint;
- subscription becomes `ACTIVE`;
- invoice becomes `PAID` at the exact configured amount and currency;
- exactly one credit grant is recorded;
- Billing summary exposes the expected entitlements;
- replaying the exact paid-invoice event returns duplicate semantics and does not grant credits again;
- evidence manifest is complete and redacted;
- operator/finance approval is attached.

Anything less remains **VALIDATION_PENDING**. Test-mode evidence can support engineering confidence but cannot convert this gate to PASS.
