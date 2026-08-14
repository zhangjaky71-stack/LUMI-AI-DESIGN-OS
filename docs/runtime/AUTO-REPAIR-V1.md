# Auto Repair Runtime V1

## Purpose

NODE-51 turns NODE-50 critique into a bounded repair workflow. It is intentionally not an autonomous infinite improve-until-happy agent. The runtime applies the smallest safe repair, evaluates the exact candidate, and only advances the Artifact branch when quality and concurrency gates permit it.

## Ownership

```text
NODE-50 Visual Critic      owns assessment + typed repair proposals
NODE-39 Constraints        owns hard preflight/postflight policy
NODE-38 Design IR          owns structural operation semantics
NODE-42 Artifact Engine    owns immutable ArtifactVersion lineage
NODE-47 Image Edit         owns local pixel-edit execution
NODE-27 Cost Ledger        owns reservation/actual financial truth (spec-only today)
NODE-32 Recipe Engine      owns higher-level bounded workflow recipes (spec-only today)
NODE-51 Auto Repair        owns repair planning, bounded iteration, comparison and promotion policy
```

NODE-51 does not reimplement provider routing, a financial ledger, Brand Rules, Identity, DesignOperation execution, or quality scoring.

## Public model

`AutoRepairLoop.run(source)` consumes:

- exact branch + expected head;
- exact ArtifactVersion/DesignDocument snapshot;
- exact NODE-50 QualityResult/profile version;
- active NODE-39 constraints;
- versioned AutoRepairPolicy.

The result contains exact initial/final version ids, initial/final quality result ids, iteration count, decimal spend, attempt history and reason codes.

## Repair actions

V1 action kinds:

1. `STRUCTURAL_DESIGN_OP` — NODE-50 frozen `DesignOperation[]`; priority 10; zero provider cost.
2. `LOCAL_IMAGE_EDIT` — image defect/composition/hierarchy pixel repair through an injected NODE-47-compatible port.
3. `RESOLUTION_UPSCALE` — export-resolution route.
4. `REGENERATE_ELEMENT` — identity-sensitive element regeneration through an injected paid port.
5. `REGENERATE_ARTIFACT` — expensive fallback capability; not selected by default V1 mappings.
6. `MANUAL_REVIEW` — fail-closed endpoint for unsupported/unsafe cases.

Brand/Logo/QR/locked-content problems are never guessed by a generic generator. If NODE-50/NODE-43/NODE-39 did not produce a safe typed structural operation, V1 routes them to review rather than inventing a destructive repair.

## Planner ordering

The planner is deterministic:

```text
lowest priority number
→ highest expected gain
→ stable item id
```

Every candidate has an async canonical SHA-256 fingerprint. A fingerprint attempted earlier in the same loop is not repeated.

## Structural execution

Structural repair calls NODE-39 `guardedExecute(document, operations, constraints)`.

A `DENY`, stale operation version, lock violation, conflict or failed NODE-38 execution prevents candidate materialization. The source document remains unchanged.

## Paid repair budget boundary

Costs are decimal strings and are converted to integer micro-dollars using `BigInt`; JS floating-point arithmetic is not used for policy accounting.

Before any paid generative repair:

```text
loop remaining budget
+ external BudgetReservationPort.remaining
→ reserve(estimated)
→ execute paid repair
→ settle(actual)
```

Execution without a reservation is an error. If NODE-27 is unavailable, paid repair is unavailable; structural zero-cost repair may still run. NODE-51 does not create a second ledger.

## Candidate lifecycle

A critical invariant is:

```text
materialize
→ persist new ArtifactVersion as DRAFT, OFF HEAD
→ add EDITED_FROM lineage with repair metadata
→ evaluate exact candidate through NODE-50
→ compare source/candidate
→ CAS promote only if accepted
```

Artifact `EDITED_FROM` is used because the existing frozen Artifact lineage enum does not define `REPAIRED_FROM`. Repair semantics are carried in edge metadata (`repair_loop_id`, `repair_item_id`, action kind, source quality id).

Rejected and review candidates remain audit evidence and never replace the active branch head.

## Quality comparison

Candidate is rejected when:

- it introduces a new Hard violation;
- it remains `FAIL_HARD`;
- score regresses beyond `max_score_regression`;
- it fails `minimum_expected_gain` while still repairable.

`REVIEW_REQUIRED` returns control to a human/policy workflow and is not auto-promoted.

A `PASS` or `PASS_WITH_WARNINGS` candidate is promoted READY. A materially improved `FAIL_REPAIRABLE` candidate may be promoted DRAFT so a later bounded iteration can repair another independent issue.

## Concurrency

The runtime checks the expected branch head before work. Production promotion is additionally transactional CAS:

```sql
UPDATE artifact_branches
SET head_version_id = :candidate
WHERE head_version_id IS NOT DISTINCT FROM :expected;
```

Zero rows means a user/agent edit won the race. `promote_auto_repair_candidate` raises `AUTO_REPAIR_BRANCH_HEAD_CAS_CONFLICT`; the candidate remains off-head and the loop returns `STALE_SOURCE`.

## Loop bounds

A policy must define:

- `max_auto_repair_iterations` (V1 hard schema max 10; production profiles use 2–3);
- `max_repair_cost_usd`;
- `minimum_expected_gain`;
- `max_score_regression`.

The loop never recursively calls itself and never retries the same fingerprint.

## Persistence

`0010_auto_repair.sql` adds:

- exact-version `auto_repair_policies`;
- `auto_repair_loops`;
- `auto_repair_attempts`;
- transactional `promote_auto_repair_candidate` CAS function.

It stores repair cost facts for audit only. NODE-27 remains financial source of truth.

## Observability

`autoRepairTelemetry()` exposes only safe aggregate facts:

- loop id/status;
- iteration/attempt counts;
- decimal spend;
- action kinds;
- promotion/rejection counts;
- reason codes.

It does not emit image bytes/URLs, prompts, user text, provider responses or secrets.

## Tests and release gates

Unit/integration coverage includes:

- real NODE-50 text critique → NODE-39 structural repair → re-evaluation → READY;
- quality regression rollback;
- new QR Hard rollback;
- cumulative DRAFT improvement then READY;
- budget exhaustion;
- reserve-before-paid ordering;
- concurrent user edit CAS loss;
- NODE-39 lock denial;
- exact micro-dollar arithmetic;
- 2,000-node structural repair scale harness.

NODE-05 has `auto-repair@1.0.0` with eight recorded release-gate scenarios. The candidate fixes the cumulative-repair case missing from the pre-NODE-51 baseline without worsening safety guardrails.

## Production adapter obligations

A production Artifact repository must persist candidate versions off-head and use the SQL CAS function or an equivalent transaction. A production paid adapter must connect BudgetReservationPort to NODE-27 once that node is implemented and GenerativeRepairPort to Tool/Model Gateway + NODE-47 capabilities. No direct provider SDK belongs in this package.
