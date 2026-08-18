# NODE-51 — Auto Repair Implementation & Acceptance Evidence

> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Branch: `feat/node-51-auto-repair`  
> Stack base: `feat/node-50-visual-critic`  
> Migration: `20260818_0020` → `20260818_0019`

## 1. What is implemented

NODE-51 is implemented as a bounded orchestration layer. It does not replace NODE-27, NODE-38, NODE-39, NODE-42, NODE-47, or NODE-50. It coordinates those systems and fails closed when an authoritative dependency is unavailable.

### Core loop

`AutoRepairEngine` performs at most one candidate repair per `resume()` call:

1. Load an exact failing ArtifactVersion and exact NODE-50 QualityResult.
2. Require the source to still be the original branch head.
3. Select the cheapest untried safe repair class.
4. Estimate cost.
5. Fall back to a free repair when a paid repair exceeds remaining budget.
6. Run NODE-39 preflight.
7. Fork an isolated repair branch.
8. Reserve a NODE-27 repair-budget envelope before paid work.
9. Execute one candidate.
10. Reconcile downstream paid-side-effect evidence.
11. Run NODE-39 postflight.
12. Run NODE-50 on the exact candidate ArtifactVersion.
13. Reject new HARD violations, score regression, or insufficient gain.
14. If candidate passes, stage an exact final version on the original branch without moving its head.
15. Run NODE-50 again on that exact staged final version.
16. Mark the staged version READY/APPROVED only after its own QualityResult passes.
17. CAS-advance the original branch head as the final atomic promotion step.

The loop is capped by the policy snapshot at 1–3 iterations and by total repair budget.

## 2. Repair planning

The deterministic planner currently prioritizes:

1. `COPY_TYPOGRAPHY_FIX`
2. `STRUCTURAL_DESIGN_OP`
3. `LOCAL_IMAGE_EDIT`
4. `REGENERATE_ELEMENT`
5. `REGENERATE_ARTIFACT`
6. `MANUAL_REVIEW`

The planner skips an exact directive/action/target/parameter signature that has already been attempted. A protected `REPLACE_ASSET` is interpreted as a free structural restore instead of a generative replacement.

## 3. NODE-38 structural repairs

`Node38StructuralRepairBackend` is a real typed Design IR path, not JSON mutation.

Implemented behavior:

- exact DesignDocumentVersion load and content-hash check;
- allowlisted directive → `DesignOperation` compilation;
- UUIDv7 `DesignOperationBatch`;
- `apply_batch()` execution;
- no-op rejection;
- immutable off-head DesignDocumentVersion creation;
- mandatory new preview through `DesignPreviewRenderPort`;
- repair-branch ArtifactVersion creation through NODE-42;
- provenance/lineage preservation.

Allowlisted operations include text replacement, resize, x/y/rotation movement, selected font/spacing properties, color, image asset replacement, and a narrow `SET_PROPERTY` list. Unknown raw property mutation fails closed.

## 4. NODE-47 local image repair

NODE-47 gained an optional `target_branch_id`. Normal Image Edit behavior is unchanged when it is omitted.

For Auto Repair:

- the target branch must belong to the same organization and Artifact;
- the branch head must be the exact source version;
- the existing ImageEdit pipeline is reused for authorization, planning, provider execution, postflight, Artifact completion, and provider cost projection;
- the returned ArtifactVersion must remain inside the requested repair branch;
- a still-pending provider result becomes `RepairSideEffectUncertain`, then NODE-51 enters reconciliation/manual review rather than replaying the paid request.

`RepairImageEditContextPort` is the safety boundary for exact NODE-45 SourceImageRef, mask, protected regions, brand rules, identity requirements, and constraints.

## 5. Budget semantics

NODE-51 uses `PostgresCostGateway` directly for a repair-loop budget envelope.

Important monetary invariant:

- the repair envelope prevents NODE-51 from starting paid work beyond its own remaining budget;
- NODE-47/NODE-46 + Model Gateway remain authoritative for provider ActualCost;
- after downstream provider settlement evidence exists, NODE-51 releases the envelope instead of writing a second ActualCost;
- unknown/uncertain paid side effects are never silently released and never blindly replayed;
- actual candidate cost is still accumulated against the repair-loop policy budget.

This avoids double-accounting while preserving loop-level spend control.

## 6. Exact-version promotion and rollback safety

The final version path intentionally does **not** call ordinary NODE-42 append-to-head before validation.

`PostgresStagedArtifactRepository` extends NODE-42 persistence with:

- `stage_version`: locks the branch, verifies expected head, allocates the next version number, writes immutable version/files/lineage/provenance/outbox, but does not advance head;
- `advance_head_to_staged`: requires the staged version to be APPROVED, requires its parent to still equal the expected head, then performs the final CAS head update.

This closes two otherwise dangerous races:

- candidate passes on a repair branch but a cloned main version has not itself been evaluated;
- a DRAFT/failed final version temporarily becomes main branch head.

An early or late user edit causes `STALE_CONFLICT`; the staged version remains non-head.

## 7. Persistence and restart safety

Migration `20260818_0020` adds:

- `repair_policy_snapshots`;
- `auto_repair_jobs`;
- `auto_repair_attempts`;
- `repair_learning_signals`.

Persistence invariants include:

- organization + operation idempotency;
- immutable policy version/hash;
- attempt sequence 1–3;
- append-only attempt payloads;
- exact source/candidate/promoted ArtifactVersion references;
- candidate and promoted QualityResult references stored separately;
- READY requires a final ArtifactVersion;
- PROMOTED requires promoted ArtifactVersion + promotion QualityResult;
- non-negative estimated/actual cost;
- valid score ranges.

The JSON codec round-trips the complete job, source snapshots, exact quality references, candidates, attempts, promotion evidence, canonical violation codes, and reason codes.

## 8. Learning signal governance

Each attempt produces a deterministic learning signal.

It stores:

- canonical `violation_code` values for aggregation;
- source violation UUIDs separately for event traceability;
- repair plan/action;
- before/after scores;
- candidate and QualityResult references;
- decision/reason codes.

Training eligibility defaults to false. Human feedback is append-only. `eligible_for_training=true` requires both a recorded human ACCEPTED/REJECTED decision and an explicit governance approval reference. Feedback collection is therefore not treated as automatic training authorization.

## 9. Submitted regression coverage

### Service-level

`services/auto-repair/tests/test_engine.py` covers:

- operation idempotency;
- candidate + exact staged final version both must pass;
- staged final quality failure cannot promote;
- early and late user-edit stale conflicts;
- new HARD violation rollback;
- budget shortage before execution;
- reserve → execute → downstream-settlement ordering;
- uncertain paid side effect is not released or replayed;
- actual-cost overrun;
- same failed directive not executed twice.

`services/auto-repair/tests/test_planner_and_codec.py` covers:

- free typography before paid local edit;
- protected asset structural restore;
- duplicate directive suppression;
- full restart codec including canonical violation code and exact promotion audit fields.

### API-level

`apps/api/tests/test_node51_auto_repair_contracts.py` covers:

- `target_branch_id` participates in Image Edit semantic identity;
- empty target branch is rejected;
- NODE-38 raw/unregistered SET_PROPERTY is rejected;
- local image edit requires a NODE-51 budget envelope;
- the envelope is not forwarded as a second NODE-47 provider settlement mechanism.

### Static architecture validator

`tools/node51/validate_auto_repair.py` verifies the migration chain and the critical architectural strings/absence conditions for staged promotion, budget ownership, branch isolation, structural fail-closed behavior, persistence, and learning governance.

## 10. What is intentionally not claimed complete

The following are real production gaps, not documentation omissions:

1. **Design IR raster preview renderer** — the repo does not yet expose a production Design IR → raster preview implementation. `DesignPreviewRenderPort` is mandatory and fail-closed; old previews are never reused for repaired Design IR.
2. **NODE-45 repair source/mask composition** — `RepairImageEditContextPort` still needs the production composition that resolves authorized exact SourceImageRef, protected regions, and safe mask from Asset Intelligence / constraint data.
3. **Regeneration backends** — `REGENERATE_ELEMENT` and `REGENERATE_ARTIFACT` remain behind the executor backend contract; the safe branch/cost/quality loop exists, but concrete NODE-46 regeneration composition is not yet wired in NODE-51.
4. **Real provider acceptance** — no claim is made that a real paid image-edit provider has completed the NODE-51 end-to-end acceptance scenario on this branch.
5. **Human/golden evaluation** — no real human accept/reject dataset or golden repair uplift report has yet been produced; synthetic/unit evidence is not presented as production calibration.
6. **Workspace lock integration** — `services/auto-repair` is intentionally not added as a uv workspace member until `uv lock` can be regenerated by a real toolchain; tests/type-checking use explicit source paths meanwhile.
7. **Hosted CI infrastructure** — prior NODE-50 runs failed before any step executed. NODE-51 must record its own actual GitHub run/job evidence before any COMPLETE claim.

## 11. Completion gate

NODE-51 may move from `IMPLEMENTED / VALIDATING` to `COMPLETE` only after all of the following are evidence-backed:

- NODE-51 contract/test jobs actually execute and pass on Hosted CI;
- PostgreSQL migration `0020` is applied and schema constraints verified;
- concrete Design IR preview renderer is composed and tested;
- concrete NODE-45 repair context/mask resolver is composed and tested;
- concrete regeneration backend is composed or explicitly removed from the enabled policy surface;
- at least one real paid local-image repair completes with cost reconciliation evidence;
- golden/human repair evaluation demonstrates improvement without protected-content regression;
- auto-repair package is added to workspace lock via real `uv lock` regeneration.

Until then, the correct status remains **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
