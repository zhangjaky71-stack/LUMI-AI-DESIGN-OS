# NODE-73 — Final Release Acceptance Ledger

Acceptance status: **NOT ACCEPTED**

Source-closure status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This is the canonical release-acceptance ledger for NODE-73. No source change, mock, test-mode payment, static validator, local-only test, template or partially completed drill may change the acceptance status to PASS by itself. Every mandatory gate must be proven against one frozen **source release candidate (source RC)**.

## Release identity model

Final Acceptance separates product code identity from later evidence commits:

| Field | Required value |
|---|---|
| Repository | `zhangjaky71-stack/LUMI-AI-DESIGN-OS` |
| Final base branch | `node-73-final-acceptance-release` |
| Current hard-stop source branch | `fix/final-acceptance-hard-stops` |
| Current hard-stop PR | `#80` |
| Source RC Git SHA | **PENDING — freeze only after every source fix including `uv.lock`** |
| Source RC version | **PENDING — root `VERSION` at source RC** |
| Source RC migration head | **PENDING — repository unique Alembic head at source RC** |
| Evidence checkout Git SHA | **PENDING — descendant of source RC with `reports/`-only committed changes** |
| Production deployment identifier | **PENDING** |
| Final evidence generation time | **PENDING** |

The canonical final runner requires the source RC to exist and be an ancestor of the evidence checkout. Between source RC and evidence checkout, committed changes are allowed only under `reports/`. Any post-RC source/config/lock/workflow/IaC change invalidates the source RC. The final checkout must also be clean, and root `VERSION` plus the unique Alembic head must still match the source RC tuple.

This avoids both stale-RC evidence reuse and an impossible self-referential rule where the release manifest would need to name the commit containing itself.

## Acceptance invariant

A mandatory gate has only these acceptance outcomes:

- `PASS`: exact-source-RC evidence proves the behavior;
- `FAIL`: exact-source-RC evidence proves it is incorrect;
- `BLOCKED_EXTERNAL`: an external account, credential, approval, provider or environment dependency prevents execution.

`SOURCE_IMPLEMENTED`, `VALIDATION_PENDING`, mocked tests, zero-step CI, staging-only evidence or documentation are not PASS.

## Mandatory automated gates

| Gate | Current status | Required PASS evidence |
|---|---|---|
| Root dependency lock freshness | **FAIL / SOURCE BLOCKER** | Root `uv.lock` genuinely regenerated before source-RC freeze using Python 3.12 and uv 0.11.28; no hand editing |
| Canonical frozen install | **PENDING** | `uv sync --all-packages --frozen` on exact source RC |
| Ruff | **PENDING** | canonical CI PASS |
| Pyright | **PENDING** | canonical CI PASS |
| Python/unit/integration test suite | **PENDING** | canonical CI PASS |
| Alembic metadata drift | **PENDING** | `alembic check` PASS after applying all migrations |
| Migration upgrade/downgrade smoke | **PENDING** | canonical PostgreSQL acceptance PASS |
| Terraform format/validate/plan | **PENDING** | exact-source-RC production/staging IaC evidence |
| Canonical GitHub Actions CI | **BLOCKED_EXTERNAL** | runner allocated and required workflows execute successfully |
| Final Product Acceptance source contract | **BLOCKED_EXTERNAL** | source contract executes final/signoff/manual-evidence/identity negative drills |
| Final Browser Preflight | **BLOCKED_EXTERNAL** | branded Chrome/Edge + Firefox/WebKit preflight executes; WebKit result is not Safari acceptance evidence |
| Structured manual evidence gate | **PENDING** | `manual-evidence-decision.json` reports `passed=true` for source RC |
| Source-RC/evidence-checkout identity gate | SOURCE_IMPLEMENTED / **PENDING** | clean evidence checkout descends from source RC with reports-only post-RC changes; VERSION/Alembic head unchanged; all six upstream decisions same RC |
| `make release-gate` | **PENDING** | exact-source-RC release-gate PASS |

The guarded lock repair entry point is:

```bash
scripts/regenerate-root-uv-lock.sh
```

It requires Python 3.12.x, uv exactly 0.11.28, clean manifest/lock inputs, `uv lock`, `uv lock --check`, `uv sync --all-packages --frozen`, complete workspace membership and no collateral source changes. The current ChatGPT execution environment exposes uv 0.10.0, so it must not be used to generate the release lock.

Latest confirmed hosted workflow evidence shows the GitHub account payment/spending-limit failure before runner allocation (`runner_id=0`, `steps=[]` on confirmed runs). Until a newly allocated runner executes real steps, hosted CI remains `BLOCKED_EXTERNAL`, not code FAIL and not PASS.

## Required upstream gates

The release manifest must freeze exactly these six decisions:

```text
security
recovery
performance
ai_regression
staging_acceptance
production_deployment
```

**All six** must include the identical source RC tuple `(git_sha, version, migration_head)`, `passed=true`, a concrete `decision_id`, and frozen evidence refs. Security/Recovery evidence cannot be reused from an older RC merely because its source gate still looks green.

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

The Stripe gate is PASS only after `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` is completed against the source RC and proves:

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
14. evidence contains no payment credentials, secrets, cookies, CSRF tokens, authorization headers or full Checkout URL.

Test-mode Checkout, mocked Stripe transport and local PostgreSQL acceptance are engineering evidence only.

## Canonical product/UAT matrix

`final/acceptance/manifest-v1.json` contains **50 scenarios**. Final Acceptance explicitly requires:

| Canonical scenario | Priority | Current status | Required evidence |
|---|---:|---|---|
| `UAT-01` core source-RC product UAT | P0 / Critical | **PENDING** | project -> agent -> generation -> Canvas -> Artifact/Version -> export plus error/retry/reconnect |
| `BILLING-UX-01` Billing UX | P0 / High | **PENDING** | plan display, auth, Checkout, success/cancel, Portal, cancellation, idempotency, CSRF/Origin, errors |
| `BROWSER-01` Chrome + Edge | P0 / High | **PENDING** | real-browser records with exact browser/OS versions and PASS |
| `BROWSER-02` Safari + Firefox | P0 / High | **PENDING** | real-browser records with exact browser/OS versions; WebKit cannot substitute Safari |
| `RESPONSIVE-01` mobile/responsive | P1 / Medium | **PENDING** | real client evidence if PASS, or complete desktop-only non-critical defer metadata |
| `A11Y-01` accessibility critical paths | P0 / High | **PENDING** | keyboard/focus/semantics/contrast/screen-reader evidence; real assistive technology + version |

Execution procedure: `docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md` and `docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md`.

### Evidence skeleton rule

Create the initial matrix **at source-RC freeze time** with:

```bash
python3 scripts/create-final-acceptance-evidence.py --release-id <release-id>
```

The generator derives source RC Git SHA, root VERSION and unique Alembic head from the repository and initializes all scenarios to `NOT_RUN`. Optional identity flags are assertions only. It writes only under `reports/final-acceptance/<release-id>/` and refuses overwrite.

After that freeze, evidence may be committed under `reports/` only. Manual evidence records retain the source RC tuple, not the later evidence-checkout SHA.

### Structured manual evidence rule

The five mandatory manual P0 scenarios each reference exactly one JSON under:

```text
reports/final-acceptance/<release-id>/manual/
```

using `final/acceptance/manual-evidence-record-template.json`. The structured gate validates source RC identity, PASS status, tester, environment, UTC timing, required UAT/Billing checks, real browser/device metadata, screen-reader metadata and nested evidence hashes.

It fails closed on duplicate identities, malformed release IDs, wrong RC, missing browser versions, WebKit-only Safari substitution, missing screen-reader version, missing mandatory checks and responsive PASS without a real client.

## Mandatory evidence-backed signoffs

The final release manifest must freeze exactly eight signed decision records by `{path, sha256}`:

| Role | Acceptance status | Required evidence |
|---|---|---|
| Product | **PENDING** | scope/UAT/customer-facing decision |
| Engineering | **PENDING** | source RC/build integrity, migrations, CI/release gate, architecture decision |
| Design | **PENDING** | visual/editable-product interaction quality and accepted design scope |
| Security | **PENDING** | security release posture and safety-control evidence |
| Operations | **PENDING** | deploy/rollback/alert/recovery/on-call readiness |
| Legal/Privacy | **PENDING** | privacy/retention/data-processing/terms/rights decision |
| Finance/Billing | **PENDING** | approved live Stripe Prices/charge and billing evidence |
| Release Owner | **PENDING** | confirms all mandatory evidence binds one source RC and authorizes final decision |

Each record uses `final/acceptance/signoff-record-template.json` and binds the same `release_id` and **source RC** Git SHA/version/migration head. The later evidence checkout SHA is not substituted into signoff `release_candidate` fields.

## Required evidence package

At minimum freeze:

- `reports/nodes/NODE-73/hard-stops-source-closure.md`;
- `reports/nodes/NODE-73/uat-signoff-source-closure.md`;
- `reports/nodes/NODE-73/final-identity-source-closure.md`;
- provider daily hard-stop runtime evidence;
- sandbox runtime/network evidence;
- rollback drill evidence;
- alert machine delivery + human acknowledgement;
- Stripe live-purchase redacted manifest and DB verifier output;
- canonical CI and Final Browser Preflight run IDs;
- `make release-gate` output;
- 50-scenario acceptance evidence;
- structured manual records and `manual-evidence-decision.json`;
- eight frozen signoff records;
- source RC SHA + evidence checkout SHA + production deployment identity;
- `final-decision.json` from the canonical runner.

## Decision rule

Final Acceptance may change from **NOT ACCEPTED** to **ACCEPTED** only when every mandatory P0/High/Critical item and required upstream/safety/signoff gate passes with frozen evidence for one source RC, there is no unresolved mandatory `FAIL` or `BLOCKED_EXTERNAL`, and the canonical runner executes from a clean evidence checkout that descends from that source RC with only `reports/` changes after the freeze.

Until then, NODE-73 remains **NOT ACCEPTED**.
