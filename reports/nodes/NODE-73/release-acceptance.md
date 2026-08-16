# NODE-73 — Final Release Acceptance Ledger

Acceptance status: **NOT ACCEPTED**

Source-closure status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This file is the canonical release-acceptance ledger for NODE-73. No source change, mock, test-mode payment, static validator, local-only test, or partially completed drill may change the acceptance status to PASS by itself. Every mandatory gate must be proven against the exact release candidate identified in the final evidence manifest.

## Release candidate identity

| Field | Required value |
|---|---|
| Repository | `zhangjaky71-stack/LUMI-AI-DESIGN-OS` |
| Final base branch | `node-73-final-acceptance-release` |
| Current hard-stop source branch | `fix/final-acceptance-hard-stops` |
| Current hard-stop PR | `#80` |
| Candidate Git SHA | **PENDING — freeze only after all source fixes are complete** |
| Production deployment identifier | **PENDING** |
| Final evidence generation time | **PENDING** |

## Acceptance invariant

A mandatory gate has only three valid states:

- `PASS`: exact-release evidence exists and proves the required behavior;
- `FAIL`: exact-release evidence proves the behavior is incorrect;
- `BLOCKED_EXTERNAL`: source work is ready but an external account, credential, approval, billing, provider, or environment dependency prevents execution.

`SOURCE_IMPLEMENTED`, `VALIDATION_PENDING`, mocked tests, static scans, staging-only results, or documentation alone are not release acceptance states and never imply `PASS`.

## Mandatory automated gates

| Gate | Current status | Required PASS evidence |
|---|---|---|
| Root dependency lock freshness | **FAIL / SOURCE BLOCKER** | Root `uv.lock` regenerated from current workspace with Python 3.12 and uv 0.11.28; no hand editing |
| Canonical frozen install | **PENDING** | `uv sync --all-packages --frozen` on exact candidate |
| Ruff | **PENDING** | canonical CI PASS |
| Pyright | **PENDING** | canonical CI PASS |
| Python/unit/integration test suite | **PENDING** | canonical CI PASS |
| Alembic metadata drift | **PENDING** | `alembic check` PASS after applying all migrations |
| Migration upgrade/downgrade smoke | **PENDING** | canonical PostgreSQL acceptance PASS |
| Terraform format/validate/plan | **PENDING** | exact-candidate production/staging IaC evidence |
| Canonical GitHub Actions CI | **BLOCKED_EXTERNAL** | runner allocated and required workflows complete successfully |
| `make release-gate` | **PENDING** | exact-candidate release-gate PASS |

GitHub Actions has previously failed before runner allocation because of the repository/account billing or spending-limit condition. Until a newly allocated runner executes the jobs, that condition is `BLOCKED_EXTERNAL`; it is not a test PASS or code FAIL.

## Mandatory production safety gates

| Gate | Source status | Acceptance status | Required runtime evidence |
|---|---|---|---|
| Provider daily dollar hard stop | SOURCE_IMPLEMENTED | **PENDING** | reviewed caps enabled; concurrent exact-provider/day denial proof; actual settlement accounting proof |
| Sandbox egress isolation | SOURCE_IMPLEMENTED | **PENDING** | deployed isolated SG/subnets/endpoints; allowed internal dependencies succeed; arbitrary internet/PostgreSQL/undeclared access fails; flow evidence archived |
| Production rollback | SOURCE_IMPLEMENTED | **PENDING** | non-no-op rollback from exact frozen predeploy state; ECS steady state and readiness recovery; evidence artifact archived |
| Alert firing and machine delivery | SOURCE_IMPLEMENTED | **PENDING** | controlled ALARM -> delivery -> OK sequence proves SNS/SQS delivery on exact deployed stack |
| Human on-call delivery and acknowledgement | SOURCE_IMPLEMENTED / DESTINATION_EXTERNAL | **PENDING** | approved human destination receives and acknowledges a drill notification |
| Stripe production billing source | SOURCE_IMPLEMENTED | **PENDING** | production live secrets/config deployed; startup live Price reconciliation succeeds |
| Stripe real live purchase | SOURCE_IMPLEMENTED | **PENDING** | one approved real payment; signed live webhooks; ACTIVE subscription; PAID invoice; exact one credit grant; replay remains DUPLICATE |

## Stripe live-purchase acceptance contract

The Stripe gate is PASS only if `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` is completed against the exact release candidate and the redacted evidence proves all of the following:

1. production uses an approved `sk_live_...` credential and production webhook signing secret;
2. the production webhook endpoint is pinned to the source-supported Stripe API version;
3. the configured live Stripe Price matches immutable LUMI price, USD currency, recurrence interval, interval count, billing scheme and usage type;
4. authenticated Checkout uses only the server-owned Price and requires `Idempotency-Key`;
5. repeating the same Checkout request with the same idempotency key resolves to the same Stripe operation rather than a second payable operation;
6. one operator-approved real payment succeeds;
7. signed live `customer.subscription.created` and `invoice.paid` events are durably stored once;
8. subscription state becomes `ACTIVE` on the expected immutable plan version;
9. invoice state becomes `PAID` at the exact configured amount and currency;
10. the invoice grants exactly the plan-defined credits once;
11. Billing summary exposes the expected plan/entitlements;
12. resending the exact paid-invoice event produces duplicate semantics and does not increase credits again;
13. `scripts/verify_stripe_live_purchase_db.py` reports `STRIPE_LIVE_PURCHASE_DB_PASS` before and after replay;
14. no payment credential, secret, cookie, CSRF token, authorization header, or full Checkout URL is stored in acceptance evidence.

Test-mode Checkout, mocked Stripe transport, synthetic webhook HMAC tests, or local PostgreSQL acceptance are engineering gates only and cannot satisfy this live-payment gate.

## Mandatory product/UAT gates

| Gate | Acceptance status | Required evidence |
|---|---|---|
| Core end-to-end product UAT | **PENDING** | approved UAT matrix for project -> agent -> generation -> canvas -> artifact/export flows |
| Billing UX UAT | **PENDING** | plan display, Checkout redirect, success/cancel, Portal, cancellation lifecycle, error/retry states |
| Cross-browser desktop | **PENDING** | approved matrix for current supported Chrome/Edge/Safari/Firefox policy |
| Cross-browser mobile/responsive | **PENDING** | approved mobile/responsive matrix where product scope requires it |
| Accessibility critical paths | **PENDING** | keyboard/focus/semantics/contrast/critical screen-reader checks |
| Performance/reliability acceptance | **PENDING** | agreed latency/load/error-budget acceptance evidence |

## Mandatory signoff gates

| Gate | Acceptance status | Required evidence |
|---|---|---|
| Product owner signoff | **PENDING** | named approver + timestamp + approved candidate SHA |
| Design signoff | **PENDING** | named approver + timestamp + approved candidate SHA |
| Operations/SRE signoff | **PENDING** | named approver + timestamp + approved candidate SHA |
| Security signoff | **PENDING** | named approver + timestamp + approved candidate SHA |
| Legal/privacy/terms signoff | **PENDING** | named approver + timestamp + approved policy/version references |
| Finance/billing signoff | **PENDING** | Stripe live Price/charge approval + billing evidence reference |

## Required evidence records

The final evidence package must reference, at minimum:

- `reports/nodes/NODE-73/hard-stops-source-closure.md`;
- provider daily hard-stop runtime evidence;
- sandbox network/runtime evidence;
- rollback drill evidence;
- alert firing/delivery/human acknowledgement evidence;
- Stripe live purchase redacted manifest and DB verifier output;
- canonical CI workflow/run IDs;
- `make release-gate` output;
- final UAT/cross-browser evidence;
- required signoffs;
- exact release SHA and production deployment identity.

## Decision rule

Final Acceptance may change from **NOT ACCEPTED** to **ACCEPTED** only when every mandatory item above is `PASS`, there are no unresolved mandatory `FAIL` or `BLOCKED_EXTERNAL` states, the evidence package refers to one exact release candidate, and the final evidence generator has been rerun after the last candidate change.

Until then, NODE-73 remains **NOT ACCEPTED**.
