# Auto Repair Runtime V1

## Runtime contract

NODE-51 is a bounded orchestration runtime around authoritative subsystems. It executes at most one repair candidate per `resume()` and persists the resulting attempt before another iteration can be selected.

```text
failed exact ArtifactVersion + exact QualityResult
  → deterministic RepairPlanner
  → remaining budget / policy
  → NODE-39 preflight
  → isolated NODE-42 repair branch
  → one repair executor
     ├─ NODE-38 typed DesignOperation batch
     ├─ NODE-47 local image edit
     └─ NODE-46 regeneration backend contract
  → NODE-39 postflight
  → NODE-50 exact candidate QualityResult
  → reject regression/new HARD/insufficient gain
  → stage exact final version on original branch (not head)
  → NODE-50 exact final-version QualityResult
  → READY/APPROVED staged version
  → NODE-42 final CAS head promotion
```

## Invariants

1. Maximum auto-repair iterations are policy bounded to 1–3.
2. One resume call performs at most one candidate repair.
3. Paid work requires a NODE-27 repair-budget reservation before execution.
4. Provider ActualCost remains owned by the downstream media/gateway path; NODE-51 does not double-book it.
5. Unknown paid side-effect state is never blindly replayed.
6. All candidates are immutable ArtifactVersions on isolated repair branches.
7. A candidate QualityResult cannot approve a different cloned final ArtifactVersion.
8. The exact staged final ArtifactVersion receives its own NODE-50 QualityResult.
9. A staged final version does not become branch head before exact quality approval.
10. Final branch-head change is CAS against the head captured when repair started.
11. A new HARD violation or unacceptable quality regression rejects the candidate.
12. Authoritative constraint unavailability fails closed to review.
13. Learning signals use canonical violation codes; training remains disabled until explicit human decision plus governance approval.

## Status model

```text
PLANNED
RUNNING
READY
REVIEW_REQUIRED
FAILED
BUDGET_EXHAUSTED
STALE_CONFLICT
CANCELLED
```

`READY` requires a final exact ArtifactVersion. `STALE_CONFLICT` means a user or another writer changed the original branch head before final promotion; repair never overwrites that newer head.

## Repair priority

```text
COPY_TYPOGRAPHY_FIX
STRUCTURAL_DESIGN_OP
LOCAL_IMAGE_EDIT
REGENERATE_ELEMENT
REGENERATE_ARTIFACT
MANUAL_REVIEW
```

The planner skips an exact previously attempted directive signature and prefers free/reversible repairs before paid generation.

## Paid side-effect semantics

NODE-51 reserves a repair-loop envelope using NODE-27 before calling a paid media path. NODE-47/NODE-46 Model Gateway execution writes the authoritative provider cost. Once a concrete provider request/cost projection exists, NODE-51 releases its envelope and increments only its own loop spend from the downstream cost evidence. If the provider may have started but completion/cost is uncertain, the job becomes `REVIEW_REQUIRED` with `COST_RECONCILIATION_REQUIRED`; the request is not repeated automatically.

## Exact promotion protocol

```text
repair-branch candidate PASS
  → stage final ArtifactVersion on original branch
       parent = original expected head
       status = DRAFT
       branch head unchanged
  → evaluate exact staged version with NODE-50
  → require same quality profile/calibration semantics and PASS
  → READY → APPROVED
  → CAS branch head expected_old → staged_version
```

A failure anywhere before the final CAS leaves the previous main head unchanged.

## Persistence

Migration `20260818_0020` persists versioned policy snapshots, jobs, append-only attempts, candidate/final quality evidence, budget/cost data, stale/reconciliation decisions, and governed learning signals.

## Known composition gaps

The runtime intentionally fails closed around unresolved production composition. See `reports/nodes/NODE-51/gap-ledger.json` and `docs/nodes/NODE-51-AUTO-REPAIR-IMPLEMENTATION.md` for the current renderer, Asset Intelligence context, regeneration, provider, human-eval, workspace-lock, and Hosted CI gaps.
