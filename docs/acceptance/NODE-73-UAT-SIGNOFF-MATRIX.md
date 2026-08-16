# NODE-73 — UAT, Browser, Accessibility & Signoff Matrix

Status: **SOURCE IMPLEMENTED / EXECUTION PENDING**

This document is the operator matrix behind `final/acceptance/manifest-v1.json`. It does not turn any scenario into PASS. Every result must come from one frozen **source release candidate (source RC)** and be frozen by path + SHA-256 from `acceptance-evidence.json`.

## 1. Release identity

Before testing, freeze exactly one source RC:

- source RC Git SHA;
- root `VERSION`;
- unique Alembic migration head;
- production deployment ID;
- production domain;
- immutable image/task-definition identities.

Evidence and signoff files may be committed after that source RC, but only as `reports/` changes. Their later evidence-checkout Git SHA is **not** a replacement for the source RC SHA recorded inside UAT/signoff records.

If any non-`reports/` source path changes after RC freeze—including application/service code, scripts, workflows, IaC, Final Acceptance definitions, `VERSION` or `uv.lock`—the source RC is invalid and affected UAT/signoffs must be rerun against the new RC.

## 2. Core product UAT — `UAT-01`

P0 / Critical. Required result: PASS.

Run the complete user path on the exact source RC:

1. authenticate and select/create an organization/project;
2. create a project from a natural-language brief;
3. run Agent planning/research/creative direction;
4. exercise approval/pause/resume;
5. perform image/design generation;
6. open the result in editable Canvas;
7. edit through Layers/Inspector rather than raster replacement only;
8. create immutable Artifact/Design versions;
9. compare/restore versions;
10. run critic/constraint/brand/identity checks;
11. repair a failing result where supported;
12. export at least the supported primary formats;
13. verify Agent Timeline/provenance/cost visibility;
14. verify primary failure/retry/reconnect states do not dead-end the user.

Required evidence includes source RC identity, test actor/organization, timestamps, project/artifact IDs, appropriate screenshots/recordings and machine/runtime evidence for paid-side-effect/idempotency behavior.

## 3. Billing UX — `BILLING-UX-01`

P0 / High. Required result: PASS.

Validate:

- current plan and available immutable plan versions display correctly;
- unauthorized actors cannot manage billing;
- Checkout uses only server-owned Price configuration;
- missing `Idempotency-Key` is rejected;
- same `Idempotency-Key` retry resolves to the same Stripe operation;
- Stripe-hosted Checkout redirect works;
- success/cancel return paths do not directly grant entitlement;
- signed webhook state becomes visible in Billing summary;
- Billing Portal opens for the correct customer;
- cancellation-at-period-end state is represented correctly;
- invalid CSRF and invalid/missing browser Origin fail closed for cookie-authenticated writes;
- provider/network failures expose actionable non-secret errors;
- no secret, payment credential or full Checkout URL leaks into acceptance evidence.

The real charge is governed separately by `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` and remains mandatory.

## 4. Desktop browser matrix

### `BROWSER-01` — Chrome + Edge

P0 / High. Capture exact browser version, OS version and test timestamp for each browser.

Required critical journeys:

- sign-in/session continuity;
- Projects and AI Workspace;
- Agent streaming/reconnect;
- Canvas select/pan/zoom/edit;
- Layers and Inspector;
- upload and download/export;
- Chinese IME text entry/edit;
- Chinese and Latin font rendering/loading;
- approval/version/compare;
- Billing read/manage according to role.

### `BROWSER-02` — Safari + Firefox

P0 / High. Capture exact-version evidence and execute core create/edit/export on real supported Safari and Firefox.

Playwright WebKit is Safari-engine preflight only. It cannot satisfy real Safari evidence.

Any browser-specific High/Critical failure blocks acceptance until fixed and rerun on the resulting new source RC where applicable.

## 5. Responsive/mobile — `RESPONSIVE-01`

P1 / Medium.

If mobile/responsive is launch scope, validate declared breakpoints, touch interaction, dialogs, navigation, upload, result review and billing-safe read flows on real declared devices/browsers.

If initial release is explicitly desktop-only, this may be `DEFERRED_NON_CRITICAL` only with complete owner/reason/impact/target-release/workaround metadata and a supported-device statement.

## 6. Accessibility critical paths — `A11Y-01`

P0 / High. Required result: PASS with zero unresolved High/Critical accessibility blocker.

Verify at minimum:

- complete keyboard reachability;
- visible focus/logical focus order;
- no keyboard trap;
- accessible names for actionable controls;
- semantic heading/landmark/dialog structure;
- status/error messaging exposed to assistive technology;
- contrast for primary text, controls, focus and error states;
- supported zoom/reflow behavior;
- a real screen-reader smoke path for critical journeys.

Automation may support evidence, but manual keyboard and screen-reader checks are required. Record the real assistive technology name and exact version.

## 7. Structured evidence identity

Each structured manual evidence record must bind the **source RC**, for example:

```json
{
  "schema_version": 1,
  "scenario_id": "UAT-01",
  "status": "PASS",
  "release_candidate": {
    "git_sha": "<source-rc-sha40>",
    "version": "<root-version-at-source-rc>",
    "migration_head": "<unique-alembic-head-at-source-rc>"
  },
  "environment": "production|production-like-staging",
  "started_at_utc": "<ISO UTC Z>",
  "completed_at_utc": "<ISO UTC Z>",
  "tester": "<identity>",
  "observations": [],
  "evidence_refs": []
}
```

The final `acceptance-evidence.json` freezes each evidence file by path + SHA-256. A PASS without frozen evidence is rejected.

Do not put the later evidence-checkout HEAD into `release_candidate.git_sha`. The canonical runner separately records and validates the evidence checkout as an evidence-only descendant of the source RC.

## 8. Mandatory signoffs

Final Acceptance requires exactly eight evidence-backed signoffs:

1. `product`;
2. `engineering`;
3. `design`;
4. `security`;
5. `operations`;
6. `legal_privacy`;
7. `finance_billing`;
8. `release_owner`.

Use `final/acceptance/signoff-record-template.json` and store completed records under:

```text
reports/final-acceptance/<release-id>/signoffs/<role>.json
```

Every record must contain:

- the same `release_id`;
- the exact same **source RC** Git SHA, version and migration head;
- the expected role;
- `status: APPROVED`;
- a named approver;
- ISO-8601 UTC `Z` approval time;
- a concrete decision;
- at least one frozen evidence reference.

Freeze every signoff record in `release-manifest.json` as `{path, sha256}`. Editing a signoff after freezing invalidates the hash and requires re-freezing/re-evaluation.

## 9. Signoff evidence expectations

- **Product:** scope, UAT, customer-facing behavior, known gaps.
- **Engineering:** source RC/build integrity, migrations, CI/release gate, architecture deviations.
- **Design:** visual quality, editable Canvas/Artifact experience and critical interaction quality.
- **Security:** security gate, tenant isolation, secrets, sandbox, auth/payment controls and vulnerability posture.
- **Operations:** deploy/rollback, alerting/on-call, backup/recovery, observability and watch readiness.
- **Legal/Privacy:** privacy/retention/data processing, policies, rights and launch commitments.
- **Finance/Billing:** approved live Stripe Prices/charge and billing/accounting evidence.
- **Release Owner:** confirms every mandatory gate/signoff references the same frozen source RC and authorizes final decision execution.

The gate verifies structure, source-RC binding and hashes. It never impersonates or auto-approves a human role.

## 10. Evidence commit rule

After source RC freeze, UAT/signoff/runtime evidence may be committed under `reports/` only. If a defect requires a source fix, stop acceptance, make the fix, freeze a new source RC and rerun all evidence whose behavior or approval could be affected.

The canonical final runner must execute from a clean evidence checkout that descends from the source RC with only `reports/` committed changes after that RC.

## 11. Final rule

A source-complete matrix, automated browser preflight, mock payment, template, old-RC evidence or unsigned signoff is not PASS. NODE-73 remains **NOT ACCEPTED** until all mandatory P0/High/Critical scenarios, runtime gates and all eight signoffs are frozen and accepted for one source RC.
