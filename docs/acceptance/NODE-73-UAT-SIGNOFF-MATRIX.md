# NODE-73 — UAT, Browser, Accessibility & Signoff Matrix

Status: **SOURCE IMPLEMENTED / EXECUTION PENDING**

This document is the operator matrix behind the canonical scenarios in `final/acceptance/manifest-v1.json`. It does not turn any scenario into PASS. Every result must come from the exact frozen release candidate and be referenced by path + SHA-256 from `acceptance-evidence.json`.

## 1. Release identity

Before testing, freeze exactly one:

- Git SHA;
- version;
- migration head;
- production deployment ID;
- production domain;
- immutable image/task-definition identities.

If the candidate changes after evidence collection, rerun affected UAT and all candidate-bound signoffs.

## 2. Core product UAT — `UAT-01`

P0 / Critical. Required result: PASS.

Run the complete user path on the exact candidate:

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

Required evidence must include the exact RC identity, test actor/organization, timestamps, affected project/artifact IDs, screenshots or recordings where appropriate, and machine/runtime evidence for paid-side-effect/idempotency behavior.

## 3. Billing UX — `BILLING-UX-01`

P0 / High. Required result: PASS.

Validate:

- current plan and available plan versions display correctly;
- unauthorized actors cannot manage billing;
- Checkout uses only server-owned Price configuration;
- missing `Idempotency-Key` is rejected;
- same `Idempotency-Key` retry resolves to the same Stripe operation;
- Stripe-hosted Checkout redirect works;
- success and cancel return paths are understandable and do not directly grant entitlement;
- signed webhook state becomes visible in Billing summary;
- Billing Portal opens for the correct customer;
- cancellation-at-period-end state is represented correctly;
- invalid CSRF and invalid/missing browser Origin fail closed for cookie-authenticated writes;
- provider/network failures produce actionable non-secret error states;
- no secret, payment credential or full Checkout URL leaks into acceptance evidence.

The real charge itself is governed separately by `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` and remains mandatory for the live-payment gate.

## 4. Desktop browser matrix

### `BROWSER-01` — Chrome + Edge

P0 / High. Capture exact browser version, OS version and test timestamp for each browser.

Required critical journeys:

- sign-in/session continuity;
- Projects and AI Workspace;
- Agent streaming/reconnect;
- Canvas select/pan/zoom/edit;
- Layers and Inspector;
- file upload and download/export;
- Chinese IME text entry/edit;
- Chinese and Latin font rendering/loading;
- approval/version/compare;
- Billing read/manage according to role.

### `BROWSER-02` — Safari + Firefox

P0 / High. Safari is no longer a deferrable P1 item for Final Acceptance. Capture the same exact-version evidence and execute the core create/edit/export journey on current supported Safari and Firefox.

Any browser-specific High/Critical failure blocks acceptance until fixed and rerun.

## 5. Responsive/mobile — `RESPONSIVE-01`

P1 / Medium.

If mobile/responsive use is within frozen launch scope, validate supported breakpoints, touch interaction, dialogs, navigation, upload, result review and billing-safe read flows on the declared device/browser matrix.

If the initial release is explicitly desktop-only, this item may be `DEFERRED_NON_CRITICAL` only with complete gap metadata: owner, reason, impact, target release and documented workaround/supported-device statement. It cannot be silently omitted.

## 6. Accessibility critical paths — `A11Y-01`

P0 / High. Required result: PASS with zero unresolved High/Critical accessibility blocker.

At minimum verify on critical paths:

- complete keyboard reachability;
- visible focus and logical focus order;
- no keyboard trap in dialogs/Canvas-adjacent controls;
- accessible names for actionable controls;
- semantic heading/landmark/dialog structure where applicable;
- status/error messaging exposed to assistive technology;
- contrast for primary text, controls, focus and error states;
- zoom/reflow behavior for supported desktop scope;
- a critical screen-reader smoke path for sign-in/project creation/result review/export/billing-safe navigation.

Automation may support evidence, but manual keyboard and screen-reader checks are required for final critical-path acceptance.

## 7. Evidence result shape

Each scenario evidence file should include at least:

```json
{
  "schema_version": 1,
  "scenario_id": "UAT-01",
  "status": "PASS|FAIL|BLOCKED_EXTERNAL|DEFERRED_NON_CRITICAL",
  "release_candidate": {
    "git_sha": "<sha40>",
    "version": "<version>",
    "migration_head": "<head>"
  },
  "environment": "production|production-like-staging",
  "started_at_utc": "<ISO UTC>",
  "completed_at_utc": "<ISO UTC>",
  "tester": "<identity>",
  "observations": [],
  "evidence_refs": []
}
```

The final `acceptance-evidence.json` must freeze the file by path + SHA-256. A PASS without frozen evidence is rejected by the final gate.

## 8. Mandatory signoffs

Final Acceptance now requires eight evidence-backed signoffs:

1. `product`;
2. `engineering`;
3. `design`;
4. `security`;
5. `operations`;
6. `legal_privacy`;
7. `finance_billing`;
8. `release_owner`.

Use `final/acceptance/signoff-record-template.json`. Store completed records under the exact release directory, for example:

```text
reports/final-acceptance/<release-id>/signoffs/product.json
reports/final-acceptance/<release-id>/signoffs/engineering.json
reports/final-acceptance/<release-id>/signoffs/design.json
reports/final-acceptance/<release-id>/signoffs/security.json
reports/final-acceptance/<release-id>/signoffs/operations.json
reports/final-acceptance/<release-id>/signoffs/legal_privacy.json
reports/final-acceptance/<release-id>/signoffs/finance_billing.json
reports/final-acceptance/<release-id>/signoffs/release_owner.json
```

Every record must contain:

- the same `release_id` as the release manifest;
- the exact same Git SHA, version and migration head;
- the exact expected role;
- `status: APPROVED`;
- a named approver;
- an ISO-8601 UTC timestamp ending in `Z`;
- a concrete decision statement;
- at least one evidence reference with path + SHA-256.

The final release manifest stores each signoff record as a frozen `{path, sha256}` reference. Editing a signoff after freezing invalidates the hash and requires re-freezing/re-evaluation.

## 9. Signoff evidence expectations

- **Product:** core scope, UAT, customer-facing behavior, known gaps.
- **Engineering:** exact build/RC integrity, migrations, CI/release gate, architecture deviations.
- **Design:** visual quality, editable Canvas/Artifact experience, critical interaction quality and accepted design scope.
- **Security:** release security gate, tenant isolation, secrets, sandbox, auth/payment controls and unresolved vulnerability posture.
- **Operations:** deploy/rollback, alerting/on-call, backup/recovery, observability and first-day watch readiness.
- **Legal/Privacy:** privacy/retention/data processing, terms/policies, asset/content rights and any required regional/customer commitments for launch scope.
- **Finance/Billing:** approved production Stripe prices/charge, billing/accounting expectations and bounded live-purchase evidence.
- **Release Owner:** confirms every mandatory gate refers to the same release candidate and authorizes final decision execution.

The gate verifies record structure, binding and evidence hashes. It does not impersonate or auto-approve any human role.

## 10. Final rule

A source-complete matrix, automated browser test, mock payment, template file or unsigned signoff is not PASS. NODE-73 remains **NOT ACCEPTED** until all mandatory P0 scenarios and all eight signoffs are frozen and accepted for one exact release candidate.
