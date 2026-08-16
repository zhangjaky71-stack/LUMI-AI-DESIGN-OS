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

Include primary failure, retry and reconnect paths. Follow `docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md`.

## 11. Execute Billing UX and Stripe live purchase

`BILLING-UX-01` is P0/High and covers plan display, role authorization, Checkout, success/cancel, Portal, cancellation lifecycle, idempotency, CSRF/Origin and actionable failure states.

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

`BROWSER-01` is P0/High for current supported Chrome and Edge. `BROWSER-02` is P0/High for current supported Safari and Firefox; Safari is no longer a deferrable P1 final-acceptance item.

Capture exact browser/OS versions and verify critical create/edit/export, Canvas, IME/font, upload/download, approval/version and Billing-safe flows.

## 13. Execute responsive/mobile scope

`RESPONSIVE-01` is P1/Medium. If mobile/responsive is launch scope, run the declared device/browser matrix. If the release is explicitly desktop-only, a defer is allowed only with complete non-critical gap metadata and a documented supported-device statement.

## 14. Execute accessibility critical paths

`A11Y-01` is P0/High. Require zero unresolved High/Critical accessibility blocker and verify at minimum:

- keyboard reachability and no traps;
- visible/logical focus;
- accessible names and semantic structure;
- assistive-technology status/error exposure;
- contrast/focus/error visibility;
- supported zoom/reflow;
- critical screen-reader smoke path.

Manual keyboard and screen-reader checks remain required even when automation is used.

## 15. Execute remaining canonical matrix

Use `final/acceptance/manifest-v1.json` as the only scenario authority. It also covers architecture, Agent authority, Design/Canvas quality, security, reliability, provenance/data lifecycle, cost controls, performance/capacity, recovery, observability, production operations, documentation and operational handoff.

Every PASS requires at least one frozen evidence reference with path + SHA-256.

## 16. Gap policy

Only genuinely non-critical P1/P2 items may use `DEFERRED_NON_CRITICAL` or `BLOCKED_EXTERNAL`, and must include:

```text
owner
reason
impact
target_release
workaround
```

P0 and Critical/High items cannot be deferred or externally blocked into a green release.

## 17. Production safety proof

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

## 18. Cost and billing reconciliation

For real accepted runs, reconcile Provider Request -> Generation -> Idempotency Operation -> Cost Ledger -> AgentRun/Task -> Billing/Credit. Any estimated value must expose confidence/reconciliation status. Unexplained material spend blocks release.

The platform-wide daily provider-dollar hard stop must be proven at a durable runtime boundary.

## 19. Security STOP-SHIP conditions

Stop on cross-tenant leak, sandbox escape, secret exposure, prompt-injection authority escalation, SSRF to metadata/private targets, payment/credit replay, or any unresolved Critical/High issue not permitted by an explicit release policy.

## 20. Freeze acceptance evidence

When all scenario statuses are final, compute the exact SHA-256 of `acceptance-evidence.json` and freeze its path/hash in `release-manifest.json`. Any subsequent edit requires a new hash and re-evaluation.

Freeze all upstream decisions and the Production deployment manifest the same way.

## 21. Complete eight evidence-backed signoffs

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

## 22. Complete operational handoff

Assign:

- on-call owner;
- support owner;
- incident commander rotation;
- first-day watch owner;
- quality/cost review owner;
- security/dependency review owner;
- DR drill owner;
- capacity review owner.

## 23. Run canonical final source gate

The GitHub `Final Product Acceptance Gate` must execute on an allocated runner using Python 3.12 and uv 0.11.28 with:

```bash
uv sync --all-packages --frozen
python3 scripts/validate_final_acceptance_contract.py
```

A `runner_id=0 / steps=[]` account Billing failure is `BLOCKED_EXTERNAL`, not source validation.

## 24. Run final decision

```bash
python3 scripts/final-acceptance-gate.py \
  --release reports/final-acceptance/<release-id>/release-manifest.json \
  --evidence reports/final-acceptance/<release-id>/acceptance-evidence.json \
  --output reports/final-acceptance/<release-id>/final-decision.json
```

Or use the manual `Final Product Acceptance Gate` workflow with the two frozen files.

## 25. Decision handling

If the gate exits non-zero or reports any blocker, the required headline remains:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Do not delete scenarios, weaken P0 priorities or edit signoff/evidence hashes to obtain green.

Only a decision with `accepted=true`, `passed=true` and `blockers=[]` may emit:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

## 26. Post-acceptance cadence

After a real accepted release, continue weekly provider/cost/quality review, monthly security/dependency review, quarterly DR drills, AI release gates for production AI changes, capacity review and governed customer-feedback learning.

## 27. Current project state

Current source work does **not** satisfy runtime/manual acceptance. GitHub hosted jobs remain externally blocked before runner allocation by the account Billing/spending-limit condition, root `uv.lock` remains stale, and required real cloud/payment/UAT/signoff evidence is still pending.

Therefore the current outcome remains:

# NOT ACCEPTED — SEE BLOCKING GAPS
