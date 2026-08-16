# NODE-73 — UAT & Signoff Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record does not change Final Acceptance to PASS.

## Gap found

The previous Final Acceptance source baseline had three release-control mismatches:

1. the canonical matrix treated Chrome/Edge as P0 but Safari as a deferrable P1 item, and did not independently require Firefox, Billing UX or critical-path Accessibility;
2. the release manifest accepted five plain `APPROVED` strings and therefore did not require Design, Legal/Privacy or Finance/Billing signoff, a named approver, timestamp, release-candidate binding or frozen signoff evidence;
3. the existing Playwright configuration/CI only used a single default browser for most E2E coverage, so it could not serve as a repeatable cross-browser regression preflight for Final Acceptance.

These were source/control-plane gaps, not merely missing runtime evidence.

## Source closure now implemented

### Canonical 50-scenario matrix

`final/acceptance/manifest-v1.json` now contains 50 scenarios and explicitly includes:

- `UAT-01` — P0/Critical exact-RC core product UAT;
- `BILLING-UX-01` — P0/High Billing UX;
- `BROWSER-01` — P0/High current supported Chrome + Edge with exact browser versions;
- `BROWSER-02` — P0/High current supported Safari + Firefox with exact browser versions;
- `RESPONSIVE-01` — P1/Medium declared responsive/mobile scope, with only complete non-critical desktop-only defer allowed;
- `A11Y-01` — P0/High keyboard/focus/semantics/contrast/zoom/critical screen-reader acceptance.

P0 must PASS, Critical/High cannot be deferred/blocked into green, and every PASS requires frozen evidence refs.

### Automated browser preflight

Added `playwright.final-acceptance.config.ts` with projects for:

- branded Google Chrome stable channel;
- branded Microsoft Edge stable channel;
- Playwright Firefox engine;
- Playwright WebKit Safari-engine preflight.

The selected smoke corpus exercises App Shell, Projects, AI Workspace, Canvas, Layers/Inspector, Versions, Export and Billing surfaces.

Added `.github/workflows/final-browser-preflight.yml` to:

- perform frozen pnpm install;
- install browser/system runtimes;
- capture Node/pnpm/Playwright/OS/browser inventory;
- run the selected corpus across all four projects;
- archive traces/screenshots/videos on failures.

`webkit-safari-engine-preflight` is explicitly **not** accepted as proof that real macOS Safari passed `BROWSER-02`; real Safari evidence remains mandatory. The workflow is a regression preflight, not a replacement for exact-browser final UAT.

Added `scripts/validate_final_browser_preflight.py`, and the Final Product Acceptance source-contract job now validates this browser preflight contract.

### Evidence-backed signoffs

`final/acceptance/release-manifest-template.json` now requires exactly eight frozen signoff specs:

- `product`;
- `engineering`;
- `design`;
- `security`;
- `operations`;
- `legal_privacy`;
- `finance_billing`;
- `release_owner`.

`final/acceptance/signoff-record-template.json` defines the signed record shape.

`final-acceptance-gate.py` now validates for every role:

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

### Negative contract drills

`validate_final_acceptance_contract.py` now constructs evidence-backed signoff fixtures and adds fail-closed drills for:

- missing Design approval;
- Finance/Billing not approved;
- Legal/Privacy approval bound to a different RC;
- Product approval with invalid/non-UTC timestamp;
- Design approval whose nested evidence hash is substituted;
- all previous P0/upstream/Production/evidence substitution drills.

The validator requires the 50-scenario matrix and the new UAT/browser/accessibility scenario IDs.

### Canonical dependency gate

`.github/workflows/final-acceptance-gate.yml` pins Python 3.12, uv 0.11.28 and `uv sync --all-packages --frozen`, aligning Final Product Acceptance with the canonical workspace dependency rule used by the hard-stop workflow.

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
- run real supported Safari on macOS; do not substitute WebKit preflight for Safari evidence;
- execute Billing UX and real Stripe live-purchase evidence;
- provide any in-scope responsive/mobile evidence or a valid P1 desktop-only defer record;
- obtain all eight real human signoffs after the evidence they approve is frozen;
- freeze every signoff record by SHA-256 in the release manifest;
- rerun the final machine decision after the last candidate/evidence/signoff change.

## Current status

NODE-73 remains **NOT ACCEPTED**. Source controls now prevent the final release from becoming green merely because a single browser passed or a handful of approval strings were changed to `APPROVED`.
