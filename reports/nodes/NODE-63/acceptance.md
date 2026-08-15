# NODE-63 — Billing Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

Implementation commit: `8bdca29afd5f9a7cb9b985ca1c98136eda6963e3`

- formal PlanVersion/BillingAccount/Subscription/Credit/Pricing/Usage/Invoice/PaymentEvent domain implemented;
- provider cost, customer usage, customer billing and credits remain separate truths;
- immutable PlanVersion and exact subscription pinning;
- exact invoice PlanVersion pinning prevents delayed old-plan invoices from granting current-plan credits;
- entitlement lookup by key instead of plan-name branching;
- immutable Credit Ledger and rebuildable balance projection;
- atomic non-negative credit consumption boundary;
- atomic refund limit boundary prevents concurrent over-refund;
- versioned usage-to-credit pricing policy and usage idempotency-key reuse protection;
- REFUND appends a new ledger entry and preserves old CONSUME;
- MockPaymentProvider hosted checkout/portal/cancel/webhook flow;
- payment webhook signature/state verification, payload hash and provider-event idempotency;
- same provider event id with a different payload hash fails closed;
- invoice credit grant has independent immutable idempotency key;
- raw payment-instrument credentials excluded from Billing product/API/domain schema;
- hosted billing/invoice links render only when HTTPS;
- `0013_billing.sql` adds durable billing schema and credit balance view;
- `/app/billing` product UX replaces placeholder;
- server-computed `can_manage` contract; API remains authoritative;
- NODE-27 provider cost reconciliation is a read-only integration port and is not simulated as implemented cost truth;
- deterministic browser fixture gated by non-production `LUMI_BILLING_E2E=1`;
- no package.json / pnpm-lock / uv.lock change required.

## Validation staged

- Project Core billing domain tests, including delayed invoice and concurrent credit/refund races;
- FastAPI billing/payment webhook tests;
- PostgreSQL migration/projection checks;
- frontend billing contract/gateway units;
- Billing browser E2E/mobile;
- production fixture-leak scan;
- prior NODE-62 through NODE-54 regressions.

These suites are **STAGED**, not observed PASS, because the hosted runner did not start.

## Hosted pinned validation evidence

Workflow: **Billing**  
Run: `31872468443`  
Run number: `1`  
Head SHA: `8bdca29afd5f9a7cb9b985ca1c98136eda6963e3`

| Job | Job/check ID | Result | Execution evidence |
| --- | ---: | --- | --- |
| `billing-contract` | `94983120575` | failure | `runner_id=0`, `runner_name=""`, `steps=[]` — runner never started |
| `billing-build` | `94983127108` | skipped | dependency did not run |
| `billing-db` | `94983127152` | skipped | dependency did not run |
| `billing-quality` | `94983127170` | skipped | dependency did not run |
| `billing-backend` | `94983127338` | skipped | dependency did not run |
| `billing-browser-e2e` | `94983127549` | skipped | dependencies did not run |

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Classification: **BLOCKED BEFORE RUNNER**.

This is an account/platform validation blocker. It is **not** a NODE-63 code/test failure and it is **not** a PASS. No checkout, dependency install, validator, pyright, unit/API test, PostgreSQL migration, production build, or browser E2E step executed in this hosted run.

## Explicit production integration gates

- [ ] durable PostgreSQL BillingRepository with transaction/locking semantics;
- [ ] deployed NODE-16 billing.read/billing.manage actor resolver;
- [ ] NODE-27 actual Provider Cost Ledger runtime/reconciliation adapter;
- [ ] model/generation/tool paths quote/consume before paid provider invocation;
- [ ] versioned failure-refund policy connected to generation workflows;
- [ ] real Payment Provider sandbox + merchant credentials/secrets;
- [ ] provider webhook retry/reconciliation operations;
- [ ] annual-plan monthly credit scheduler/policy if YEAR billing is enabled;
- [ ] jurisdiction-specific tax/invoice configuration reviewed;
- [ ] hosted pinned gates execute green.

The MockPaymentProvider and in-memory repository are deterministic development/test evidence only. They are not represented as production money movement, PCI compliance certification, provider-cost ledger completion or transactional database proof.

## Definition of Done

- [x] customer billing domain implemented;
- [x] immutable plan/credit semantics;
- [x] hosted payment boundary;
- [x] webhook idempotency contract;
- [x] insufficient-credit preflight guard;
- [x] delayed invoice exact PlanVersion semantics;
- [x] concurrent refund limit semantics;
- [x] Billing Center UX;
- [x] tests/API/DB/browser gates staged;
- [ ] production adapters connected;
- [ ] real provider sandbox accepted;
- [ ] hosted pinned validation observed green.
