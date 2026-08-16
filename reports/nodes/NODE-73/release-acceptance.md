# NODE-73 — Final Release Acceptance Ledger

Acceptance status: **NOT ACCEPTED**

Source-closure status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This is the canonical release-acceptance ledger for NODE-73. No source change, mock, test-mode payment, static validator, local-only test, template or partially completed drill may change the acceptance status to PASS by itself. Every mandatory gate must be proven against one exact release candidate.

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

A mandatory gate has only these acceptance outcomes:

- `PASS`: exact-release evidence proves the behavior;
- `FAIL`: exact-release evidence proves it is incorrect;
- `BLOCKED_EXTERNAL`: an external account, credential, approval, provider or environment dependency prevents execution.

`SOURCE_IMPLEMENTED`, `VALIDATION_PENDING`, mocked tests, zero-step CI, staging-only evidence or documentation are not PASS.

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
| Canonical GitHub Actions CI | **BLOCKED_EXTERNAL** | runner allocated and required workflows execute successfully |
| Final Product Acceptance source contract | **BLOCKED_EXTERNAL** | source contract executes on runner and passes |
| `make release-gate` | **PENDING** | exact-candidate release-gate PASS |

Latest confirmed hard-stop workflow evidence still shows `runner_id=0`, `steps=[]` and the GitHub account payment/spending-limit annotation. Until a newly allocated runner actually executes the jobs, this remains `BLOCKED_EXTERNAL`, not code FAIL and not PASS.

## Mandatory production safety gates

| Gate | Source status | Acceptance status | Required runtime evidence |
|---|---|---|---|
| Provider daily dollar hard stop | SOURCE_IMPLEMENTED | **PENDING** | reviewed caps enabled; concurrent exact-provider/day denial proof; actual settlement accounting proof |
| Sandbox egress isolation | SOURCE_IMPLEMENTED | **PENDING** | deployed isolated SG/subnets/endpoints; allowed dependencies succeed; arbitrary internet/PostgreSQL/undeclared access fails; network evidence archived |
| Production rollback | SOURCE_IMPLEMENTED | **PENDING** | non-no-op rollback from exact frozen predeploy state; ECS steady state and readiness recovery |
| Alert firing and machine delivery | SOURCE_IMPLEMENTED | **PENDING** | controlled ALARM -> delivery -> OK proves deployed SNS/SQS transport |
| Human on-call delivery and acknowledgement | SOURCE_IMPLEMENTED / DESTINATION_EXTERNAL | **PENDING** | approved human destination receives and acknowledges drill notification |
| Stripe production billing source | SOURCE_IMPLEMENTED | **PENDING** | live secrets/config deployed; startup live Price reconciliation succeeds |
| Stripe real live purchase | SOURCE_IMPLEMENTED | **PENDING** | one approved real payment; signed live webhooks; ACTIVE subscription; PAID invoice; exactly one credit grant; replay remains DUPLICATE |

## Stripe live-purchase acceptance contract

The Stripe gate is PASS only after `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` is completed against the exact candidate and proves:

1. approved production `sk_live_...` credential and webhook signing secret;
2. production webhook endpoint pinned to source-supported Stripe API version;
3. live Price matches immutable LUMI amount, USD currency, recurrence, billing scheme and usage type;
4. authenticated Checkout uses server-owned Price and requires `Idempotency-Key`;
5. same Checkout idempotency key resolves to the same provider operation;
6. one bounded operator/finance-approved real payment succeeds;
7. signed live subscription-created and invoice-paid events are durably stored once;
8. subscription becomes `ACTIVE` on the expected immutable plan;
9. invoice becomes `PAID` at exact configured amount/currency;
10. invoice grants plan-defined credits exactly once;
11. Billing summary exposes expected plan/entitlements;
12. exact paid-invoice replay is `DUPLICATE` and does not increase credits;
13. `scripts/verify_stripe_live_purchase_db.py` reports PASS before and after replay;
14. acceptance evidence contains no payment credentials, secrets, cookies, CSRF tokens, authorization headers or full Checkout URL.

Test-mode Checkout, mocked Stripe transport and local PostgreSQL acceptance are engineering evidence only.

## Canonical product/UAT matrix

`final/acceptance/manifest-v1.json` now contains **50 scenarios**. In addition to the original architecture/golden-journey/security/performance/recovery/operations controls, Final Acceptance explicitly requires:

| Canonical scenario | Priority | Current status | Required evidence |
|---|---:|---|---|
| `UAT-01` core exact-RC product UAT | P0 / Critical | **PENDING** | project -> agent -> generation -> Canvas -> Artifact/Version -> export plus error/retry paths |
| `BILLING-UX-01` Billing UX | P0 / High | **PENDING** | plan display, role controls, Checkout, success/cancel, Portal, cancellation, idempotency, CSRF/Origin, errors |
| `BROWSER-01` Chrome + Edge | P0 / High | **PENDING** | exact browser/OS versions and primary create/edit/export + IME/font/upload/download evidence |
| `BROWSER-02` Safari + Firefox | P0 / High | **PENDING** | exact browser/OS versions and core create/edit/export evidence; no P1 Safari defer |
| `RESPONSIVE-01` mobile/responsive scope | P1 / Medium | **PENDING** | supported device matrix, or complete explicitly desktop-only non-critical defer metadata |
| `A11Y-01` accessibility critical paths | P0 / High | **PENDING** | keyboard/focus/semantics/contrast/zoom and critical screen-reader checks with zero High/Critical blocker |

Execution procedure: `docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md`.

## Mandatory evidence-backed signoffs

The final release manifest no longer accepts plain `"APPROVED"` strings. It must freeze eight signed decision records by `{path, sha256}`:

| Role | Acceptance status | Required evidence |
|---|---|---|
| Product | **PENDING** | scope/UAT/customer-facing decision |
| Engineering | **PENDING** | exact build/RC integrity, migrations, CI/release gate, architecture decision |
| Design | **PENDING** | visual/editable-product interaction quality and accepted design scope |
| Security | **PENDING** | security release posture and safety-control evidence |
| Operations | **PENDING** | deploy/rollback/alert/recovery/on-call readiness |
| Legal/Privacy | **PENDING** | privacy/retention/data-processing/terms/rights decision for launch scope |
| Finance/Billing | **PENDING** | approved Stripe live Prices/charge and billing evidence |
| Release Owner | **PENDING** | confirms all mandatory evidence binds one exact candidate and authorizes final decision |

Each record uses `final/acceptance/signoff-record-template.json` and must contain matching `release_id`, exact Git SHA/version/migration head, expected role, `status: APPROVED`, named approver, ISO-8601 UTC `Z` timestamp, concrete decision and at least one frozen evidence ref. Missing role, wrong RC, invalid timestamp or evidence hash mismatch blocks Final Acceptance.

The gate validates these records; it does not impersonate or auto-approve any human role.

## Required evidence records

The final evidence package must reference at minimum:

- `reports/nodes/NODE-73/hard-stops-source-closure.md`;
- provider daily hard-stop runtime evidence;
- sandbox network/runtime evidence;
- rollback drill evidence;
- alert firing/delivery/human acknowledgement evidence;
- Stripe live-purchase redacted manifest and DB verifier output;
- canonical CI workflow/run IDs;
- `make release-gate` output;
- 50-scenario final acceptance evidence including UAT/browser/accessibility;
- eight frozen signoff records;
- exact release SHA and production deployment identity.

## Decision rule

Final Acceptance may change from **NOT ACCEPTED** to **ACCEPTED** only when every mandatory P0/High/Critical item and required upstream/safety/signoff gate passes with frozen evidence for one exact release candidate, there is no unresolved mandatory `FAIL` or `BLOCKED_EXTERNAL`, and the final evidence generator/gate is rerun after the final candidate change.

Until then, NODE-73 remains **NOT ACCEPTED**.
