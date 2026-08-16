# NODE-73 — Final Product Acceptance Runbook

> Status: **SOURCE RUNBOOK / FINAL PRODUCT NOT YET ACCEPTED**

## 1. Purpose

This is the final Go/No-Go procedure for LUMI AI Design OS. It re-validates NODE-66～72 evidence together with product UAT, production safety drills, Stripe live billing, browser/accessibility evidence and cross-functional signoff.

Default outcome:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

`LUMI AI DESIGN OS — PRODUCT ACCEPTED` is reserved for a machine decision with `accepted=true`, `passed=true`, `blockers=[]` against one frozen **source release candidate (source RC)**.

## 2. Identity model: source RC + evidence checkout

Final Acceptance uses two Git identities for different purposes:

1. **source RC SHA** — the immutable product/source commit that is deployed and tested;
2. **evidence checkout SHA** — a descendant commit that may add frozen acceptance material under `reports/` only.

The release candidate identity is:

```text
source_rc_git_sha
version
migration_head
production deployment_id
production domain
immutable image/task-definition identities
```

The canonical runner requires:

- the source RC commit exists locally;
- the source RC is an ancestor of the evidence checkout;
- root `VERSION` still equals the source RC release version;
- the repository still has the same unique Alembic head;
- every committed path between `source_rc_git_sha..HEAD` is under `reports/`;
- the working tree is clean.

Therefore, **after source RC freeze, do not change `apps/`, `services/`, `scripts/`, `infra/`, workflows, `final/`, `VERSION`, `uv.lock`, or any other non-`reports/` path**. Any such source change invalidates the RC and requires a new freeze and rerun of affected evidence/signoffs.

This model intentionally allows evidence/signoff commits without creating an impossible self-referential rule where a release manifest would have to name the commit that contains itself.

## 3. Resolve source blockers before freezing the source RC

STOP before source RC freeze while any source blocker remains, including:

- stale root `uv.lock`;
- incomplete source changes;
- unresolved Critical/High code/security/reliability issues;
- inconsistent release version or migration graph.

The current root lock must be repaired **before** source RC freeze using:

```bash
scripts/regenerate-root-uv-lock.sh
```

The helper requires Python 3.12.x and uv exactly 0.11.28, runs `uv lock`, `uv lock --check`, `uv sync --all-packages --frozen`, checks every workspace member, requires an actual lock change and rejects collateral source changes. Never hand-edit `uv.lock`.

External blockers such as GitHub hosted-runner Billing/spending limits may remain `BLOCKED_EXTERNAL`, but they cannot be converted to PASS.

## 4. Freeze one exact source RC

Only after all source changes—including the regenerated `uv.lock`—are committed, record the current source RC.

At this point the repository facts become authoritative:

```text
git rev-parse HEAD
cat VERSION
unique Alembic head
```

Do not manually invent these values in evidence files. The repository tooling derives them.

From this point until final authorization, subsequent Git commits must be `reports/` evidence-only commits. If a source change is needed, stop, make the source change, freeze a new source RC and invalidate/re-evaluate affected candidate-bound evidence.

## 5. Create the 50-scenario evidence skeleton at source-RC freeze time

Run on the source RC checkout:

```bash
python3 scripts/create-final-acceptance-evidence.py \
  --release-id <release-id>
```

By default this creates:

```text
reports/final-acceptance/<release-id>/acceptance-evidence.json
```

The generator automatically derives the current Git SHA, root `VERSION` and unique Alembic head, reads `final/acceptance/manifest-v1.json`, creates all **50 scenarios** as `NOT_RUN`, and refuses to overwrite an existing evidence file.

Optional `--git-sha`, `--version` and `--migration-head` flags are assertions only; if supplied they must equal repository truth.

Commit the generated skeleton as an evidence-only `reports/` commit. `NOT_RUN` cannot satisfy Final Acceptance.

## 6. Collect all six upstream machine decisions for the same source RC

Freeze exactly these required upstream gates:

```text
security
recovery
performance
ai_regression
staging_acceptance
production_deployment
```

**All six**, including Security and Recovery, must contain the same full `release_candidate` tuple as the final source RC:

```text
git_sha
version
migration_head
```

Each decision must also contain a concrete `decision_id`, `passed=true`, and non-empty frozen `evidence_refs[]`. The canonical runner fails closed on any stale upstream RC.

## 7. Production deployment identity

The exact Production deployment manifest must exist under:

```text
reports/production-deployments/
```

It must bind the same source RC and deployment identity. Freeze it by path + SHA-256 in the final release manifest.

## 8. Execute Golden Journey A — Zero-to-Brand

Use a production-scope test account and the frozen source RC. Prove:

```text
Create Project -> Brief Agent -> sourced research -> strategy -> creative directions
-> approval -> moodboard/Brand Kit -> generation/design -> editable Canvas
-> Critic/Brand/Identity QA -> repair -> Versions/provenance -> multi-format export
-> Agent Timeline/cost/pause/resume
```

A rendered image alone is insufficient. Final assets must remain structurally editable, versioned and traceable.

## 9. Execute Golden Journey B — Precision Local Edit

Use an approved version and execute a constrained instruction such as:

> 产品和Logo都不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。

Prove product/logo/QR invariants, structural title/background edit, QR scanability, new immutable version, old-version restore and quality/constraint PASS.

## 10. Execute Golden Journey C — Multi-size Campaign

Adapt one approved design to 1:1, 4:5, 9:16 and 16:9. Prove real layout adaptation rather than naive stretching and preserve Brand/Product constraints.

## 11. Execute Golden Journey D — Failure Recovery

Inject controlled worker restart, provider timeout/429/5xx, duplicate request/event and SSE disconnect/reconnect. Prove explicit recovery without duplicate paid generation, corrupt Artifact, approved-version loss or blind ambiguous provider retry.

## 12. Execute explicit product UAT

`UAT-01` is P0/Critical. Execute:

```text
project -> agent -> generation -> canvas -> artifact/version -> compare/restore -> export
```

The structured record must include PASS checks for:

```text
project
agent
generation
canvas
artifact-version
export
error-retry-reconnect
```

Follow `docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md`.

## 13. Execute Billing UX and Stripe live purchase

`BILLING-UX-01` is P0/High. Required checks:

```text
plan-display
authorization
checkout
success-cancel
portal
cancellation
idempotency
csrf-origin
error-states
```

The real-charge gate is separately mandatory. Execute `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` and prove:

- approved production `sk_live_` mode;
- source-supported Stripe API version;
- startup Price reconciliation;
- one bounded Finance/Operations-approved real payment;
- signed live subscription/invoice webhooks;
- ACTIVE subscription;
- PAID invoice at exact configured amount/currency;
- exactly one credit grant;
- replay of the exact paid-invoice event remains DUPLICATE and grants no second credit.

Mock/test-mode evidence cannot satisfy the live-payment gate.

## 14. Execute browser matrix

`BROWSER-01` is P0/High and requires real current supported Chrome and Edge. `BROWSER-02` is P0/High and requires real current supported Safari and Firefox.

For each browser capture:

```text
browser
browser_version
os
os_version
real_browser = true
status = PASS
```

For Safari, Playwright WebKit is preflight evidence only and cannot substitute for real macOS Safari.

The automated preflight lives in `playwright.final-acceptance.config.ts` and `.github/workflows/final-browser-preflight.yml`.

## 15. Execute responsive/mobile scope

`RESPONSIVE-01` is P1/Medium. If mobile/responsive is launch scope, PASS requires real device/client evidence. If release scope is explicitly desktop-only, defer only with complete non-critical gap metadata and a supported-device statement.

## 16. Execute accessibility critical paths

`A11Y-01` is P0/High. Require zero unresolved High/Critical accessibility blocker and verify:

- keyboard reachability/no traps;
- visible/logical focus;
- accessible names/semantic structure;
- contrast/focus/error visibility;
- supported zoom/reflow;
- a real critical screen-reader smoke path.

The manual record must identify the assistive technology and exact version. Automated DOM/keyboard checks do not replace the real screen-reader test.

## 17. Freeze structured manual evidence

For mandatory manual P0 scenarios create:

```text
reports/final-acceptance/<release-id>/manual/uat-01.json
reports/final-acceptance/<release-id>/manual/billing-ux-01.json
reports/final-acceptance/<release-id>/manual/browser-01.json
reports/final-acceptance/<release-id>/manual/browser-02.json
reports/final-acceptance/<release-id>/manual/a11y-01.json
```

If `RESPONSIVE-01` is PASS, also create `manual/responsive-01.json`.

Every record must contain the **source RC** tuple, not the later evidence checkout SHA. It must also contain exact release/scenario identity, tester, UTC timestamps, environment, scenario-specific checks/clients and frozen nested evidence hashes.

Add each structured JSON to the matching `acceptance-evidence.json` scenario as `{path, sha256}`. Commit these files only under `reports/`.

## 18. Execute remaining canonical matrix

`final/acceptance/manifest-v1.json` is the only scenario authority. Every PASS needs at least one frozen evidence reference.

Only genuinely non-critical P1/P2 items may use `DEFERRED_NON_CRITICAL` or `BLOCKED_EXTERNAL`, with:

```text
owner
reason
impact
target_release
workaround
```

P0 and Critical/High items cannot be deferred/blocked into a green release.

## 19. Production safety proof

Final evidence must include real runtime proof for:

- provider daily dollar hard stop;
- sandbox egress isolation;
- production rollback drill;
- alert ALARM -> delivery -> OK machine path;
- approved human on-call delivery/acknowledgement;
- HTTPS/domain, DB/storage/broker/secrets/WAF/backups;
- exact immutable image digests and migrations;
- production smoke/canary/steady state.

Terraform/source/runbooks alone are not production evidence.

## 20. Cost and billing reconciliation

For accepted runs reconcile Provider Request -> Generation -> Idempotency Operation -> Cost Ledger -> AgentRun/Task -> Billing/Credit. The platform-wide daily provider-dollar hard stop must be proven at a durable runtime boundary.

## 21. Security STOP-SHIP conditions

Stop on cross-tenant leak, sandbox escape, secret exposure, prompt-injection authority escalation, SSRF to metadata/private targets, payment/credit replay, or unresolved Critical/High release blockers.

## 22. Freeze acceptance evidence and release manifest

When scenario statuses are final:

1. compute the exact SHA-256 of `acceptance-evidence.json`;
2. freeze its path/hash in `release-manifest.json`;
3. freeze all six upstream decisions and the Production deployment manifest by path/hash;
4. keep `release_candidate.git_sha` equal to the **source RC SHA**, even though the release manifest itself is committed later as evidence;
5. commit only under `reports/`.

Any evidence edit requires recomputing affected hashes and re-evaluating downstream signoffs.

## 23. Complete eight evidence-backed signoffs

Required roles are exactly:

```text
product
engineering
design
security
operations
legal_privacy
finance_billing
release_owner
```

Store completed records at:

```text
reports/final-acceptance/<release-id>/signoffs/<role>.json
```

Each signoff must bind the same **source RC** release ID/Git SHA/version/migration head; include a named approver, `status: APPROVED`, UTC `Z` timestamp, concrete decision and frozen evidence references.

Freeze each signoff in `release-manifest.json` as `{path, sha256}`. The gate never auto-signs or impersonates a human.

## 24. Complete operational handoff

Assign on-call, support, incident commander rotation, first-day watch, quality/cost review, security/dependency review, DR drill and capacity review owners.

## 25. Run canonical source/lock/browser gates

GitHub hosted jobs must actually receive a runner. Required source-side commands include:

```bash
uv sync --all-packages --frozen
python3 scripts/validate_final_acceptance_contract.py
python3 scripts/validate_final_manual_evidence_contract.py
python3 scripts/validate_final_browser_preflight.py
python3 scripts/validate_final_upstream_lock_contract.py
python3 scripts/validate_final_runner_checkout_binding.py
bash -n scripts/regenerate-root-uv-lock.sh
```

The separate Final Browser Preflight must run its multi-browser corpus. A `runner_id=0 / steps=[]` Billing/spending-limit failure is `BLOCKED_EXTERNAL`, not source validation.

## 26. Run the canonical final decision from a clean evidence checkout

The checkout used to authorize the release must:

- descend from the source RC;
- contain only `reports/` committed changes after the source RC;
- have no uncommitted/untracked files;
- retain the same `VERSION` and unique Alembic head.

Run:

```bash
python3 scripts/run-final-acceptance.py \
  --release reports/final-acceptance/<release-id>/release-manifest.json \
  --evidence reports/final-acceptance/<release-id>/acceptance-evidence.json \
  --manual-output reports/final-acceptance/<release-id>/manual-evidence-decision.json \
  --output reports/final-acceptance/<release-id>/final-decision.json
```

Do not call low-level `final-acceptance-gate.py` alone for release authorization.

The canonical runner first validates source-RC/evidence-checkout identity and all six upstream RC bindings, then evaluates structured manual evidence, then the low-level final matrix.

After the command writes decision files, those decision files may be committed as final evidence under `reports/`, but if a final decision is re-run later, the same source-RC/evidence-only rules still apply.

## 27. Decision handling

If any gate reports a blocker, the headline remains:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Do not delete scenarios, weaken P0 priorities, substitute WebKit for Safari, invent browser/assistive-technology versions, alter hashes, reuse stale upstream decisions or change source files after RC freeze to obtain green.

Only a canonical run where manual evidence passes and the final decision has `accepted=true`, `passed=true`, `blockers=[]` may emit:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

## 28. Current project state

Current source work does **not** satisfy runtime/manual acceptance. GitHub hosted jobs remain externally blocked before runner allocation by the account Billing/spending-limit condition, the root `uv.lock` remains stale, and required real cloud/payment/UAT/signoff evidence is still pending.

Therefore the current outcome remains:

# NOT ACCEPTED — SEE BLOCKING GAPS
