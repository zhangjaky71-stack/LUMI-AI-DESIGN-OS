# NODE-73 — Final Product Acceptance Runbook

> Status: **SOURCE RUNBOOK / FINAL PRODUCT NOT YET ACCEPTED**

## 1. Purpose

This is the final Go/No-Go procedure for LUMI AI Design OS. It freezes and re-validates the real NODE-66～72 evidence together with product UAT, production safety drills, Stripe live billing, documentation, browser/accessibility evidence and cross-functional signoff.

Default outcome:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

`LUMI AI DESIGN OS — PRODUCT ACCEPTED` is reserved for a machine decision with `accepted=true`, `passed=true`, `blockers=[]` against one exact release candidate.

## 2. Freeze one exact release candidate

Freeze exactly one identity before final evidence is accepted:

```text
git_sha
version
migration_head
production deployment_id
production domain
immutable image/task-definition identities
```

Do not mix evidence from different commits, migration heads or deployment sets. Any candidate change invalidates affected evidence and signoffs.

The exact Production deployment manifest must exist under `reports/production-deployments/` and match the same RC.

## 3. Resolve source and external blockers first

STOP final acceptance while any mandatory blocker remains, including:

- stale root `uv.lock`;
- GitHub Actions runner/account Billing blocker;
- unexecuted canonical frozen install/CI/release gate;
- missing production-like Staging decision;
- missing production deployment/canary evidence;
- unresolved Critical/High security or reliability issue.

`SOURCE_IMPLEMENTED`, `VALIDATION_PENDING`, zero-step CI, mock tests or test-mode provider evidence are not PASS.

## 4. Collect six upstream machine decisions

Freeze these six required upstream gates:

```text
security
recovery
performance
ai_regression
staging_acceptance
production_deployment
```

Each decision must include a concrete `decision_id`, `passed=true`, non-empty frozen `evidence_refs[]`, and no release blocker. Performance, AI Regression, Staging Acceptance and Production Deployment must match the exact final RC identity.

## 5. Create the final evidence skeleton

Run:

```bash
python3 scripts/create-final-acceptance-evidence.py \
  --release-id <release-id> \
  --git-sha <git-sha> \
  --version <version> \
  --migration-head <migration-head> \
  --output reports/final-acceptance/<release-id>/acceptance-evidence.json
```

The generator reads `final/acceptance/manifest-v1.json` and currently creates **50 scenarios** as `NOT_RUN`. Never replace unexecuted work with PASS to complete the matrix.

`release_id` must use only letters, digits, `.`, `_` and `-`, start with a letter/digit, and be at most 120 characters.

## 6. Execute Golden Journey A — Zero-to-Brand

Use a production-scope test account and the frozen RC. Prove the complete flow:

```text
Create Project -> Brief Agent -> sourced research -> strategy -> creative directions
-> approval -> moodboard/Brand Kit -> generation/design -> editable Canvas
-> Critic/Brand/Identity QA -> repair -> Versions/provenance -> multi-format export
-> Agent Timeline/cost/pause/resume
```

A rendered image alone is insufficient. Final assets must remain structurally editable, versioned and traceable.

## 7. Execute Golden Journey B — Precision Local Edit

Use an approved version and execute a constrained instruction such as:

> 产品和Logo都不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。

Prove product/logo/QR invariants, structural title/background edit, QR scanability, new immutable version, old-version restore and quality/constraint PASS.

## 8. Execute Golden Journey C — Multi-size Campaign

Adapt one approved design to 1:1, 4:5, 9:16 and 16:9. Prove real layout adaptation rather than naive stretching and preserve Brand/Product constraints.

## 9. Execute Golden Journey D — Failure Recovery

Inject controlled worker restart, provider timeout/429/5xx, duplicate request/event and SSE disconnect/reconnect. Prove explicit recovery without duplicate paid generation, corrupt Artifact, approved-version loss or blind ambiguous provider retry.

## 10. Execute explicit product UAT

`UAT-01` is a P0/Critical independent final gate. Execute the exact RC across:

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

## 11. Execute Billing UX and Stripe live purchase

`BILLING-UX-01` is P0/High. Its structured record must include PASS checks for:

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

The real-charge gate is separate and mandatory. Execute `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` and prove:

- approved `sk_live_` production mode;
- source-supported Stripe API version;
- startup Price reconciliation;
- one bounded approved real payment;
- signed live subscription/invoice webhooks;
- ACTIVE subscription;
- PAID invoice at exact configured amount/currency;
- exactly one credit grant;
- replay of the exact paid-invoice event remains DUPLICATE and grants no second credit.

Mock/test-mode evidence cannot satisfy the live-payment gate.

## 12. Execute browser matrix

`BROWSER-01` is P0/High and requires real current supported Chrome and Edge. `BROWSER-02` is P0/High and requires real current supported Safari and Firefox; Safari is no longer a deferrable P1 final-acceptance item.

For each required browser, structured evidence must contain:

```text
browser
browser_version
os
os_version
real_browser = true
status = PASS
```

For Safari, `engine_preflight_only=true` is explicitly rejected. Playwright WebKit is a useful automated Safari-engine preflight but cannot satisfy real macOS Safari evidence.

The automated preflight lives in `playwright.final-acceptance.config.ts` and `.github/workflows/final-browser-preflight.yml`; it complements, but does not replace, exact-browser final evidence.

## 13. Execute responsive/mobile scope

`RESPONSIVE-01` is P1/Medium. If mobile/responsive is launch scope, a PASS requires at least one real tested client/device with device, browser/browser version, OS/OS version and `real_browser=true`.

If the release is explicitly desktop-only, a defer is allowed only with complete non-critical gap metadata and a documented supported-device statement.

## 14. Execute accessibility critical paths

`A11Y-01` is P0/High. Require zero unresolved High/Critical accessibility blocker and verify at minimum:

- keyboard reachability and no traps;
- visible/logical focus;
- accessible names and semantic structure;
- contrast/focus/error visibility;
- supported zoom/reflow;
- critical screen-reader smoke path.

The structured manual record must include PASS manual checks for:

```text
keyboard
focus
semantics
contrast
screen-reader
```

The `screen-reader` check must identify the real assistive technology and its version. Automated DOM/keyboard preflight cannot replace the manual screen-reader check.

## 15. Freeze structured manual UAT evidence

For each of the five mandatory manual P0 scenarios, copy `final/acceptance/manual-evidence-record-template.json` into the exact release directory:

```text
reports/final-acceptance/<release-id>/manual/uat-01.json
reports/final-acceptance/<release-id>/manual/billing-ux-01.json
reports/final-acceptance/<release-id>/manual/browser-01.json
reports/final-acceptance/<release-id>/manual/browser-02.json
reports/final-acceptance/<release-id>/manual/a11y-01.json
```

If `RESPONSIVE-01` is PASS, also create:

```text
reports/final-acceptance/<release-id>/manual/responsive-01.json
```

Every structured record must contain:

- `schema_version: 1`;
- exact `release_id`;
- exact scenario ID;
- `status: PASS`;
- exact Git SHA/version/migration head;
- `environment` equal to `production` or `production-like-staging`;
- named tester;
- valid UTC start/end timestamps ending in `Z`;
- scenario-specific clients/checks/manual_checks;
- at least one nested evidence ref with path + SHA-256.

Then add that JSON itself to the matching scenario's `acceptance-evidence.json` `evidence_refs[]` as `{path, sha256}`. Each mandatory scenario must contain exactly one structured manual JSON under its release `manual/` directory. Duplicate scenario IDs, duplicate browser/check IDs, wrong RC, hash mismatch or malformed release directory identity fail closed.

## 16. Execute remaining canonical matrix

Use `final/acceptance/manifest-v1.json` as the only scenario authority. It also covers architecture, Agent authority, Design/Canvas quality, security, reliability, provenance/data lifecycle, cost controls, performance/capacity, recovery, observability, production operations, documentation and operational handoff.

Every PASS requires at least one frozen evidence reference with path + SHA-256.

## 17. Gap policy

Only genuinely non-critical P1/P2 items may use `DEFERRED_NON_CRITICAL` or `BLOCKED_EXTERNAL`, and must include:

```text
owner
reason
impact
target_release
workaround
```

P0 and Critical/High items cannot be deferred or externally blocked into a green release.

## 18. Production safety proof

Final evidence must include real runtime proof for:

- provider daily dollar hard stop;
- sandbox egress isolation;
- production rollback drill;
- alert ALARM -> delivery -> OK machine path;
- approved human on-call delivery/acknowledgement;
- HTTPS/domain, DB/storage/broker/secrets/WAF/backups;
- exact immutable image digests and migrations;
- production smoke/canary/steady state.

Source Terraform and runbooks alone are not production evidence.

## 19. Cost and billing reconciliation

For real accepted runs, reconcile Provider Request -> Generation -> Idempotency Operation -> Cost Ledger -> AgentRun/Task -> Billing/Credit. Any estimated value must expose confidence/reconciliation status. Unexplained material spend blocks release.

The platform-wide daily provider-dollar hard stop must be proven at a durable runtime boundary.

## 20. Security STOP-SHIP conditions

Stop on cross-tenant leak, sandbox escape, secret exposure, prompt-injection authority escalation, SSRF to metadata/private targets, payment/credit replay, or any unresolved Critical/High issue not permitted by an explicit release policy.

## 21. Freeze acceptance evidence

When all scenario statuses are final, compute the exact SHA-256 of `acceptance-evidence.json` and freeze its path/hash in `release-manifest.json`. Any subsequent edit requires a new hash and re-evaluation.

Freeze all upstream decisions and the Production deployment manifest the same way.

## 22. Complete eight evidence-backed signoffs

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

For each role, copy `final/acceptance/signoff-record-template.json` to:

```text
reports/final-acceptance/<release-id>/signoffs/<role>.json
```

Each record must bind the same `release_id`, Git SHA, version and migration head; identify a named approver; contain `status: APPROVED`; include an ISO-8601 UTC `Z` timestamp, a concrete decision and at least one frozen evidence reference.

Freeze every signoff record in `release-manifest.json` as `{path, sha256}`. Missing Design, Legal/Privacy, Finance/Billing or any other required role blocks release. The gate validates records; it never impersonates or auto-approves a human role.

## 23. Complete operational handoff

Assign:

- on-call owner;
- support owner;
- incident commander rotation;
- first-day watch owner;
- quality/cost review owner;
- security/dependency review owner;
- DR drill owner;
- capacity review owner.

## 24. Run canonical final source gate

The GitHub `Final Product Acceptance Gate` must execute on an allocated runner using Python 3.12 and uv 0.11.28 with:

```bash
uv sync --all-packages --frozen
python3 scripts/validate_final_acceptance_contract.py
python3 scripts/validate_final_manual_evidence_contract.py
python3 scripts/validate_final_browser_preflight.py
python3 scripts/validate_final_upstream_lock_contract.py
```

The separate `Final Browser Preflight` should also run the selected multi-browser regression corpus. Its WebKit result is not real Safari evidence.

A `runner_id=0 / steps=[]` account Billing failure is `BLOCKED_EXTERNAL`, not source validation.

## 25. Run final decision through the canonical runner

Do **not** call the low-level `final-acceptance-gate.py` by itself for release authorization. The canonical runner always evaluates structured manual evidence first:

```bash
python3 scripts/run-final-acceptance.py \
  --release reports/final-acceptance/<release-id>/release-manifest.json \
  --evidence reports/final-acceptance/<release-id>/acceptance-evidence.json \
  --manual-output reports/final-acceptance/<release-id>/manual-evidence-decision.json \
  --output reports/final-acceptance/<release-id>/final-decision.json
```

Or use the manual `Final Product Acceptance Gate` workflow with the two frozen files; that workflow calls the same canonical runner.

## 26. Decision handling

If the structured manual gate or final gate exits non-zero or reports any blocker, the required headline remains:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Do not delete scenarios, weaken P0 priorities, substitute WebKit for Safari, invent browser/assistive-technology versions, or edit signoff/evidence hashes to obtain green.

Only a canonical run where manual evidence passes and the final decision has `accepted=true`, `passed=true` and `blockers=[]` may emit:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

## 27. Post-acceptance cadence

After a real accepted release, continue weekly provider/cost/quality review, monthly security/dependency review, quarterly DR drills, AI release gates for production AI changes, capacity review and governed customer-feedback learning.

## 28. Current project state

Current source work does **not** satisfy runtime/manual acceptance. GitHub hosted jobs remain externally blocked before runner allocation by the account Billing/spending-limit condition, root `uv.lock` remains stale, and required real cloud/payment/UAT/signoff evidence is still pending.

Therefore the current outcome remains:

# NOT ACCEPTED — SEE BLOCKING GAPS
