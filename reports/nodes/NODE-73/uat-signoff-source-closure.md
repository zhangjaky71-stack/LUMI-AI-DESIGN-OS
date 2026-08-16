# NODE-73 — UAT & Signoff Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record does not change Final Acceptance to PASS.

## Gap found

The previous Final Acceptance source baseline had two release-control mismatches:

1. the canonical matrix treated Chrome/Edge as P0 but Safari as a deferrable P1 item, did not independently require Firefox, Billing UX or critical-path Accessibility;
2. the release manifest accepted five plain `APPROVED` strings and therefore did not require Design, Legal/Privacy or Finance/Billing signoff, a named approver, timestamp, release-candidate binding or frozen signoff evidence.

These gaps conflicted with the final release ledger and were source gaps, not merely missing runtime evidence.

## Source closure now implemented

### Canonical 50-scenario matrix

`final/acceptance/manifest-v1.json` now contains 50 scenarios and explicitly includes:

- `UAT-01` — P0/Critical exact-RC core product UAT;
- `BILLING-UX-01` — P0/High Billing UX;
- `BROWSER-01` — P0/High current supported Chrome + Edge with exact browser versions;
- `BROWSER-02` — P0/High current supported Safari + Firefox with exact browser versions;
- `RESPONSIVE-01` — P1/Medium declared responsive/mobile scope, with only complete non-critical desktop-only defer allowed;
- `A11Y-01` — P0/High keyboard/focus/semantics/contrast/zoom/critical screen-reader acceptance.

The existing fail-closed scenario rules remain: P0 must PASS, Critical/High cannot be deferred/blocked into green, and every PASS requires frozen evidence refs.

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

The validator also requires the 50-scenario matrix and the new UAT/browser/accessibility scenario IDs.

### Canonical dependency gate

`.github/workflows/final-acceptance-gate.yml` now pins:

- Python 3.12;
- uv 0.11.28;
- `uv sync --all-packages --frozen`.

This aligns Final Product Acceptance with the canonical workspace dependency rule used by the hard-stop workflow.

### Operator documentation

Added/updated:

- `docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md`;
- `docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md`;
- `reports/nodes/NODE-73/release-acceptance.md`.

## Still required before acceptance

- regenerate the stale root `uv.lock` with canonical tooling;
- restore GitHub Actions runner allocation and execute the source contract/canonical lock gate;
- freeze one exact final RC;
- execute all required P0 UAT/browser/accessibility scenarios on the exact RC;
- execute Billing UX and real Stripe live-purchase evidence;
- provide any in-scope responsive/mobile evidence or a valid P1 desktop-only defer record;
- obtain all eight real human signoffs after the evidence they approve is frozen;
- freeze every signoff record by SHA-256 in the release manifest;
- rerun the final machine decision after the last candidate/evidence/signoff change.

## Current status

NODE-73 remains **NOT ACCEPTED**. Source controls now prevent the final release from becoming green merely because Chrome/Edge passed or five approval strings were changed to `APPROVED`.
