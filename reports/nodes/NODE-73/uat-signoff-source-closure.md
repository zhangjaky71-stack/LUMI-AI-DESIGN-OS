# NODE-73 — UAT & Signoff Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record does not change Final Acceptance to PASS.

## Gaps found

The previous Final Acceptance source baseline had four release-control mismatches:

1. the canonical matrix treated Chrome/Edge as P0 but Safari as a deferrable P1 item, and did not independently require Firefox, Billing UX or critical-path Accessibility;
2. the release manifest accepted five plain `APPROVED` strings and therefore did not require Design, Legal/Privacy or Finance/Billing signoff, a named approver, timestamp, release-candidate binding or frozen signoff evidence;
3. the existing Playwright configuration/CI only used a single default browser for most E2E coverage, so it could not serve as a repeatable cross-browser regression preflight for Final Acceptance;
4. the final matrix required only an evidence file + SHA for UAT/browser/accessibility PASS, but did not validate that the evidence itself contained the required real browsers, exact versions, screen-reader identity or mandatory UAT/Billing checks.

These were source/control-plane gaps, not merely missing runtime evidence.

## Source closure now implemented

### Canonical 50-scenario matrix

`final/acceptance/manifest-v1.json` contains 50 scenarios and explicitly includes:

- `UAT-01` — P0/Critical exact-RC core product UAT;
- `BILLING-UX-01` — P0/High Billing UX;
- `BROWSER-01` — P0/High current supported Chrome + Edge with exact browser versions;
- `BROWSER-02` — P0/High current supported Safari + Firefox with exact browser versions;
- `RESPONSIVE-01` — P1/Medium declared responsive/mobile scope, with only complete non-critical desktop-only defer allowed;
- `A11Y-01` — P0/High keyboard/focus/semantics/contrast/zoom/critical screen-reader acceptance.

P0 must PASS, Critical/High cannot be deferred/blocked into green, and every PASS requires frozen evidence refs.

### Automated browser/accessibility preflight

Added `playwright.final-acceptance.config.ts` with projects for:

- branded Google Chrome stable channel;
- branded Microsoft Edge stable channel;
- Playwright Firefox engine;
- Playwright WebKit Safari-engine preflight.

The selected smoke corpus exercises App Shell, Projects, AI Workspace, Canvas, Layers/Inspector, Versions, Export, Billing and critical accessibility preflight.

Added `.github/workflows/final-browser-preflight.yml` to:

- perform frozen pnpm install;
- install browser/system runtimes;
- capture Node/pnpm/Playwright/OS/browser inventory;
- run the selected corpus across all four projects;
- archive traces/screenshots/videos on failures.

Added `apps/web/e2e/final-accessibility-preflight.spec.ts` for machine-detectable critical-path checks including main landmarks, headings, unnamed interactive controls, missing image alternatives and keyboard/focus behavior around the skip link and command dialog.

`webkit-safari-engine-preflight` is explicitly **not** accepted as proof that real macOS Safari passed `BROWSER-02`; real Safari evidence remains mandatory. Automated accessibility preflight likewise does not replace the manual screen-reader P0 requirement.

Added `scripts/validate_final_browser_preflight.py`, and the Final Product Acceptance source-contract job validates this browser/a11y preflight contract.

### Structured manual evidence gate

Added `final/acceptance/manual-evidence-record-template.json` and `scripts/final-manual-evidence-gate.py`.

The five mandatory manual P0 scenarios must each reference exactly one structured JSON under:

```text
reports/final-acceptance/<release-id>/manual/
```

The structured gate verifies:

- safe release-id syntax;
- exact release/scenario/RC identity;
- `status=PASS`;
- named tester;
- production or production-like-staging environment;
- valid ordered UTC timestamps;
- nested evidence refs + SHA-256;
- all required UAT checks;
- all required Billing UX checks;
- real Chrome/Edge/Safari/Firefox browser evidence with exact browser/OS versions;
- rejection of WebKit-only Safari substitution;
- manual keyboard/focus/semantics/contrast/screen-reader checks;
- real assistive technology name + version;
- real device/client metadata when `RESPONSIVE-01` is PASS.

It fails closed on duplicate scenario IDs, duplicate browser/check identities, malformed release IDs, wrong RC, missing browser versions, missing screen-reader version, missing mandatory checks and responsive PASS without a real client.

`validate_final_manual_evidence_contract.py` now uses a correct `<release-id>/manual/` fixture and exercises these negative cases.

### Canonical final runner

Added `scripts/run-final-acceptance.py` as the release-authorization entry point. It always runs:

```text
structured manual evidence gate -> low-level final product decision gate
```

The `Final Product Acceptance Gate` workflow and Final Acceptance Runbook now call this runner. A standalone direct call to `final-acceptance-gate.py` is not the canonical release-authorization procedure.

Both `manual-evidence-decision.json` and `final-decision.json` are archived by the workflow.

### Evidence-backed signoffs

`final/acceptance/release-manifest-template.json` requires exactly eight frozen signoff specs:

- `product`;
- `engineering`;
- `design`;
- `security`;
- `operations`;
- `legal_privacy`;
- `finance_billing`;
- `release_owner`.

`final/acceptance/signoff-record-template.json` defines the signed record shape.

`final-acceptance-gate.py` validates for every role:

- frozen record path + SHA-256 under the final release evidence root;
- schema version;
- exact `release_id`;
- exact role identity;
- `status=APPROVED`;
- named approver;
- ISO-8601 UTC `Z` approval timestamp;
- exact Git SHA/version/migration-head match;
- concrete decision;
- at least one frozen evidence reference with a valid SHA-256.

The gate does not create or impersonate human approval.

### Signoff negative contract drills

`validate_final_acceptance_contract.py` constructs evidence-backed signoff fixtures and adds fail-closed drills for:

- missing Design approval;
- Finance/Billing not approved;
- Legal/Privacy approval bound to a different RC;
- Product approval with invalid/non-UTC timestamp;
- Design approval whose nested evidence hash is substituted;
- all previous P0/upstream/Production/evidence substitution drills.

### Canonical dependency gate

Python-dependent canonical release gates now converge on:

```text
Python 3.12
uv 0.11.28
uv sync --all-packages --frozen
```

This includes canonical CI, Security, AI Regression, Staging Acceptance and Final Product Acceptance. `scripts/validate_final_upstream_lock_contract.py` prevents those required workflows from silently drifting back to older/unpinned uv behavior.

Recovery/Performance source contracts and Production deploy do not install the Python workspace and therefore are not forced through uv merely for consistency.

### Operator documentation

Added/updated:

- `docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md`;
- `docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md`;
- `reports/nodes/NODE-73/release-acceptance.md`;
- `reports/nodes/NODE-73/latest-ci-external-blocker.md`.

## Still required before acceptance

- regenerate the stale root `uv.lock` with canonical tooling;
- restore GitHub Actions runner allocation and execute source-contract/canonical lock/browser preflight jobs;
- freeze one exact final RC;
- execute all required P0 UAT/browser/accessibility scenarios on the exact RC;
- populate the structured manual evidence records and freeze them by SHA-256;
- run real supported Safari on macOS; do not substitute WebKit preflight for Safari evidence;
- perform a real supported screen-reader check and record assistive technology/version;
- execute Billing UX and real Stripe live-purchase evidence;
- provide any in-scope responsive/mobile evidence or a valid P1 desktop-only defer record;
- obtain all eight real human signoffs after the evidence they approve is frozen;
- freeze every signoff record by SHA-256 in the release manifest;
- execute the canonical final runner after the last candidate/evidence/signoff change.

## Current status

NODE-73 remains **NOT ACCEPTED**. Source controls now prevent the final release from becoming green merely because a generic file hash exists, a single browser passed, WebKit was mislabeled as Safari, a screen-reader check was omitted, or a handful of approval strings were changed to `APPROVED`.
