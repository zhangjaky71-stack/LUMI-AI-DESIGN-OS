# NODE-51 — Auto Repair Loop

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0/P1 CORE QUALITY  
> Depends on: NODE-47, NODE-50, NODE-32(spec-only adapter), NODE-27(spec-only adapter)  
> Produces: Critic → RepairPlan → guarded execution → candidate re-evaluation → CAS promotion bounded loop

## 1. Objective

Convert structured NODE-50 critique into safe automatic improvement without infinite retries, hidden spend or destructive branch overwrites.

## 2. Runtime package

`packages/auto-repair-engine` owns only loop/planner/comparison policy. It consumes existing boundaries instead of duplicating them.

## 3. Input

`RepairSource` pins:

- branch id + exact expected head;
- exact ArtifactVersion and DesignDocumentVersion;
- exact NODE-50 QualityResult/profile version;
- NODE-39 constraints.

## 4. Policy

Every run pins exact `AutoRepairPolicy` version:

```text
max_auto_repair_iterations
max_repair_cost_usd
minimum_expected_gain
max_score_regression
```

Production seeds use 2–3 iterations. Runtime refuses values outside 1–10.

## 5. Planner

Priority order:

```text
STRUCTURAL_DESIGN_OP
LOCAL_IMAGE_EDIT
RESOLUTION_UPSCALE
REGENERATE_ELEMENT
REGENERATE_ARTIFACT
MANUAL_REVIEW
```

NODE-50 typed DesignOperations are always preferred. Unsupported brand/logo/QR fixes fail closed to review unless an authoritative validator produced a safe operation.

## 6. Constraint safety

Structural operations execute only through NODE-39 `guardedExecute`. Hard locks/conflicts/stale DesignOperation versions prevent materialization.

Generative adapters are required to use the same postflight/quality boundaries before promotion; NODE-51 never declares a generated asset safe by itself.

## 7. Budget

NODE-27 is currently spec-only, therefore NODE-51 exposes `BudgetReservationPort` rather than inventing a ledger.

Paid sequence is strictly reserve → execute → settle. Without the port, paid repair is unavailable. Decimal costs use integer micro-dollars internally.

## 8. Versioning and rollback

Every repair candidate is a new immutable DRAFT ArtifactVersion persisted **off branch head** with `EDITED_FROM` repair metadata.

Only after exact NODE-50 re-evaluation may a candidate be promoted:

- PASS/WARN → READY + CAS head;
- improved FAIL_REPAIRABLE → DRAFT + CAS head for another bounded iteration;
- regression/new Hard/FAIL_HARD → rejected off-head;
- REVIEW_REQUIRED → review, no head advance.

## 9. Concurrency

Promotion uses expected-head CAS. A concurrent user/agent change wins; repair candidate is rejected/off-head and result is `STALE_SOURCE`. Repair never force-overwrites the user.

## 10. Retry/loop control

Canonical fingerprints prevent repeated identical repairs. Iteration and budget limits stop the loop deterministically.

## 11. Persistence

`db/migrations/0010_auto_repair.sql` provides policy/loop/attempt audit tables and `promote_auto_repair_candidate()` transaction function. It intentionally does not create financial ledger tables.

## 12. Observability

Safe aggregate loop telemetry includes status, iterations, spend, attempts, action kinds, promotion/rejection counts and reason codes. Raw content/prompt/provider payloads are excluded.

## 13. Tests

Implemented executable scenarios:

- real NODE-50/NODE-39 structural repair;
- worse-candidate rollback;
- new Hard violation rollback;
- two-step DRAFT→READY cumulative repair;
- budget exhausted;
- reserve-before-paid execution;
- concurrent head stale conflict;
- hard constraint deny;
- micro-dollar precision;
- 2k-node structural scale harness.

## 14. NODE-05 gate

`auto-repair@1.0.0` contains 8 baseline/candidate replay cases. Candidate improves the cumulative repair case while safety guardrails remain zero.

## 15. CI

`.github/workflows/auto-repair.yml` defines:

1. `repair-contract`
2. `repair-quality`
3. `repair-integration`
4. `repair-budget`
5. `repair-db`
6. `repair-benchmark`

Hosted jobs must actually execute green before this node can become COMPLETE.

## 16. Acceptance status

Implementation is present, but hosted execution evidence remains required. A zero-step GitHub Actions billing/spending failure is an external blocker, not code PASS or code FAIL.

## 17. Definition of Done

```text
bounded orchestrator                         IMPLEMENTED
minimal structural-first planner             IMPLEMENTED
constraint guarded execution                 IMPLEMENTED
budget reservation boundary                  IMPLEMENTED
candidate off-head + quality re-eval          IMPLEMENTED
quality rollback/new-hard rejection          IMPLEMENTED
CAS stale-user protection                    IMPLEMENTED
version lineage contract                     IMPLEMENTED
NODE-05 golden repair release gate            IMPLEMENTED
hosted six-job CI green                      PENDING VALIDATION
```

Completes Phase 6 after hosted validation. Next: NODE-52 App Shell.
