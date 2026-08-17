# NODE-50 Acceptance — Visual Critic & Design Quality Engine

## Status

**IMPLEMENTED / VALIDATING / not COMPLETE**

This record separates implementation evidence from calibration/live execution evidence. NODE-50 now contains the provider-neutral quality domain, hard-first gate, existing-engine adapters, calibrated Model Gateway critic adapter, exact ArtifactVersion binding, persistence schema, tests and CI definition. It does **not** claim real human calibration or hosted/live acceptance green.

## Implemented scope

- exact ArtifactVersion quality input; no branch-head/latest fallback;
- canonical 13 quality dimensions;
- six versioned quality profiles with exact weights/thresholds/hard dimensions;
- profile/context-aware required dimensions: generic artifacts are not forced to provide nonexistent QR/brand/identity/logo evidence;
- artifact brand/identity context adds the corresponding required quality dimensions;
- deterministic evidence evaluated before visual-model evidence;
- deterministic/authoritative signal unavailability forces `REVIEW_REQUIRED` rather than allowing VLM substitution;
- hard violations force `FAIL_HARD` and cannot be averaged away;
- NODE-39 Constraint Runtime normalization including QR/text/contrast/export dimensions;
- NODE-43 Brand compliance normalization;
- NODE-44 product/logo/character identity normalization;
- structured evidence, dimension assessments and violations;
- registered typed repair actions suitable for NODE-51 handoff;
- independent visual grader contract using NODE-22 `llm.vision`;
- calibration-pinned provider/model with fallback disabled;
- generation-model/critic-model isolation check;
- visual critic cannot emit HARD severity;
- grader timeout/unavailable/calibration mismatch -> `REVIEW_REQUIRED`, not PASS;
- low-confidence high-impact result -> `REVIEW_REQUIRED`;
- versioned grader calibration snapshot with dataset hash, FP/FN, precision/recall and inter-rater fields;
- current-calibration registry enforcement;
- deterministic QualityResult id + operation-id idempotency;
- QualityResult exact `artifact_version_id` and content-hash persistence;
- normalized dimension and violation database rows plus complete result JSON;
- Alembic `20260818_0019` directly after NODE-49 `20260817_0018`;
- deterministic scoring benchmark harness;
- dedicated contract / quality / PostgreSQL / benchmark CI definition;
- five-item production gap ledger.

## Canonical committed test intentions

The committed suite covers:

1. hard QR failure cannot be hidden by a 100 overall score;
2. hard brand font failure maps to brand consistency and blocks;
3. product identity drift is a hard failure in strict quality flows;
4. known typography overflow yields `FAIL_REPAIRABLE` with typed `SET_PROPERTY` action;
5. visual grader timeout yields `REVIEW_REQUIRED`;
6. low confidence on high-impact dimensions yields `REVIEW_REQUIRED`;
7. critic calibration id mismatch yields `REVIEW_REQUIRED`;
8. same generation and critic provider/model yields `REVIEW_REQUIRED`;
9. NODE-22 critic request is `llm.vision`, pinned to calibration and `allow_fallback=false`;
10. visual grader attempts to emit HARD are rejected;
11. exact NODE-42 ArtifactVersion lookup without branch-head resolution;
12. cross-project ArtifactVersion rejection;
13. QualityResult codec round-trip;
14. generic artifacts do not require absent QR/brand/identity dimensions;
15. artifact brand context requires brand assessment;
16. an unavailable authoritative deterministic signal forces `REVIEW_REQUIRED` even when other scores are perfect.

These are committed test intentions until an execution environment actually runs them.

## Calibration evidence status

`tools/node50/benchmark_quality_scoring.py` is a deterministic control-plane performance harness. It validates stable weighted scoring mechanics only.

It is **not** a calibrated visual-quality benchmark. No claim of production precision, false-positive rate, false-negative rate or inter-rater agreement is made from synthetic fixtures. Those values must come from a reviewed human-labeled dataset before NODE-50 can be COMPLETE.

## Hosted gates and observed execution evidence

The NODE-50 workflow requires:

- `critic-contract`
- `critic-quality`
- `critic-db`
- `critic-benchmark`

The PostgreSQL job is authored to migrate the full schema to Alembic head and verify profile/calibration/result/dimension/violation tables, exact ArtifactVersion FK and hard-block constraints.

PR #117 created NODE-50 workflow run `32081808874` (`NODE-50 Visual Critic`, run number 1). The first job, `critic-contract` job `95546109355`, completed with conclusion `failure` **before any workflow step executed**: GitHub returned an empty step list, and the job log endpoint had no log blob. The dependent `critic-quality`, `critic-db` and `critic-benchmark` jobs were therefore skipped.

The same commit also created NODE-49 run `32081808767`; its first `export-contract` job `95546107864` showed the same pre-step failure pattern and all dependent jobs were skipped. This is consistent with the repository/account pre-run infrastructure failure pattern previously confirmed on NODE-48 as a GitHub Actions Billing/Spending Limit blocker. The connector did not expose a new NODE-50 annotation naming the billing condition, so this acceptance record treats NODE-50 as **pre-run infrastructure blocked**, not as code-green or code-red execution evidence.

Accordingly, there is still no hosted pytest, Ruff, Pyright, PostgreSQL or benchmark execution evidence for NODE-50.

## Production completion gates

NODE-50 remains **not COMPLETE** until all five gap-ledger items are closed. The largest non-code gate is human calibration: representative labels, pairwise/human reviewer agreement, model-version-specific thresholds and measured FP/FN behavior are required.

Production completion also requires exact-version production adapters for the existing deterministic engines, live independent visual-grader acceptance, downstream quality/review policy integration and hosted/live infrastructure acceptance.

## Files

- `services/visual-critic/src/lumi_visual_critic/*`
- `services/visual-critic/tests/*`
- `apps/api/src/lumi_api/visual_critic/*`
- `apps/api/src/lumi_api/persistence/models_visual_critic.py`
- `apps/api/migrations/versions/20260818_0019_visual_critic.py`
- `apps/api/migrations/versions/20260818_0019_sql/*`
- `tools/node50/*`
- `docs/runtime/VISUAL-CRITIC-V1.md`
- `reports/nodes/NODE-50/gap-ledger.json`
- `.github/workflows/node-50-visual-critic.yml`

## Next node

After NODE-50 implementation validation, proceed to **NODE-51 — Auto Repair** while keeping NODE-50 calibration and production gaps visible and unclosed.
