# NODE-50 — Visual Critic Acceptance

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-49-export-engine-release@68a2500e6aa6cc1f96269410da101a9342475839`

## Implemented evidence

### Domain/runtime

- `packages/quality-engine` is a standalone quality domain package.
- QualityResult freezes exact ArtifactVersion + DesignVersion identity.
- 13 quality dimensions and 5 gate statuses are typed.
- Built-in profiles: exploration, production-web, brand-strict, product-strict, print, social-fast.
- Deterministic graders execute before subjective graders.
- NODE-39/43/44 are consumed through typed ports rather than reimplemented.
- Visual grader has separate `visual-critic` role identity, timeout and calibration/version guard.
- Same model + same prompt self-approval is rejected into review.
- Hard failures are evaluated before weighted score approval.
- Low-confidence active hard-gate evidence enters review, never silent PASS.
- Repair actions are frozen NODE-38 DesignOperations and are never executed by the critic.

### Deterministic signals

- text overflow + `RESIZE_NODE` proposal；
- node-outside-parent + `MOVE_NODE` proposal；
- exact hex contrast calculation；
- expected Design IR text presence + constrained `SET_TEXT` proposal；
- minimum export-resolution hard gate。

### Persistence

- `ArtifactEngineQualityAdapter` verifies exact scope/version identity.
- Full result is written through `QualityResultRepository`.
- ArtifactVersion summary stores `overall_score / 100` to preserve the historical 0–1 DB scale.
- Adapter does not mutate content hash, status or branch head.
- `0009_visual_critic.sql` persists profiles, calibration, results, dimensions, violations and evidence.
- DB trigger mirrors 0–100 QualityResult score to 0–1 Artifact summary.

### Calibration and benchmark

- fixed 40-sample calibration contract corpus；
- precision/recall/F1/FP/FN recomputation test；
- explicit synthetic/non-production label on the corpus；
- NODE-05 `visual-critic@1.0.0` baseline/candidate replay suite with 8 release-gate cases；
- deterministic 2,000-node scale harness without provider access。

### Security/observability

- Quality Engine contains no provider SDK integration; production model calls remain behind NODE-22 Model Gateway adapters.
- safe telemetry projection excludes prompt text, OCR text, image URLs and raw VLM responses.
- cross-project Artifact quality attachment is rejected.

## Executable test matrix

```text
hard QR failure                         -> FAIL_HARD
hard brand font violation               -> FAIL_HARD
hard product identity failure           -> FAIL_HARD
insufficient export resolution          -> FAIL_HARD
typography overflow                     -> FAIL_REPAIRABLE + RESIZE_NODE
visual grader timeout                   -> REVIEW_REQUIRED
low confidence                          -> REVIEW_REQUIRED
calibration dataset drift               -> REVIEW_REQUIRED
same model + prompt self approval       -> REVIEW_REQUIRED
hard constraint runtime unavailable     -> REVIEW_REQUIRED, never PASS
clean deterministic required dimension  -> PASS
Artifact exact persistence              -> normalized score only
```

## CI gates

`.github/workflows/visual-critic.yml` requires:

1. `critic-contract`
2. `critic-quality`
3. `critic-integration`
4. `critic-calibration`
5. `critic-db`
6. `critic-benchmark`

The DB gate applies `0001 + 0009`, inserts an exact 93-point QualityResult and checks that ArtifactVersion stores `0.93`.

The calibration gate recomputes metrics and runs NODE-05 baseline-vs-candidate comparison.

## Hosted CI evidence — initial release HEAD

Initial release HEAD: `8d500d7cf976e069173b60d7a9ee5ad4d9356d9b`

Visual Critic workflow:

```text
run_id: 31820529421
critic-contract job_id: 94832429909
critic-contract conclusion: failure
runner_id: 0
steps: []
critic-quality: skipped
critic-integration: skipped
critic-calibration: skipped
critic-db: skipped
critic-benchmark: skipped
```

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Interpretation: this is an account-level GitHub Actions billing/spending-limit blocker. The runner never started, so the architecture validator, TypeScript typecheck, unit/integration tests, calibration recomputation, NODE-05 gate, PostgreSQL migration test and benchmark were **not executed**. This is not an observed code/test failure and is not PASS.

This evidence commit intentionally creates a new final release HEAD. The final-head hosted run is recorded in PR metadata/body only rather than creating another evidence commit, preventing a commit → workflow → evidence-commit loop.

## Completion policy

This report does **not** mark NODE-50 PASS/COMPLETE merely because code/workflow files exist.

Hosted jobs must actually start and execute green on the final release HEAD. A GitHub Actions payment/spending-limit failure with `runner_id=0` / no steps remains an external CI blocker and is not an observed code/test failure.

Production VLM auto-approval additionally requires a real human-labeled calibration corpus; the committed synthetic corpus is software-contract evidence only.

## Current acceptance

```text
implementation                         IMPLEMENTED
static architecture gate               not executed on hosted runner
TypeScript typecheck                    not executed on hosted runner
unit/integration tests                  not executed on hosted runner
calibration recomputation               not executed on hosted runner
NODE-05 release gate                    not executed on hosted runner
PostgreSQL migration/trigger            not executed on hosted runner
2k-node scale harness                   not executed on hosted runner
hosted blocker                          GitHub billing/spending limit
production human VLM calibration        pending before live auto-approval
```

Overall: **IMPLEMENTED / VALIDATING / not COMPLETE**.
