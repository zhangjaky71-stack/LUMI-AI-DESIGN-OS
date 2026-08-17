# VISUAL-CRITIC-V1

## Scope

NODE-50 evaluates one exact ArtifactVersion after generation/editing and produces a versioned, evidence-backed `QualityResult`. It is a quality decision engine, not a generator, editor, Artifact approver or replacement for the authoritative Constraint/Brand/Identity engines.

## Ownership boundaries

- **NODE-39 Constraint Runtime** owns deterministic layout/constraint validation including bounds, safe areas, text overflow, contrast, QR and export dimensions.
- **NODE-43 Brand Rules** owns published brand rule sets and brand compliance truth.
- **NODE-44 Identity Engine** owns product/logo/character/face identity reference sets, thresholds and identity calibration.
- **NODE-22 Model Gateway** owns routing/transport/cost for the independent visual critic model.
- **NODE-42 Artifact Engine** owns immutable ArtifactVersion truth.
- **NODE-50** owns multi-signal normalization, hard-first quality gating, versioned quality profiles, critic calibration binding, structured critique/repair plans and durable QualityResult records.

LangSmith may receive critic traces/experiments, but QualityResult persistence must succeed independently of LangSmith availability.

## Exact ArtifactVersion invariant

Evaluation accepts an exact `artifact_version_id`. `Node42QualityArtifactAdapter` performs:

```text
get_version(exact id)
→ get_artifact(version.artifact_id)
→ verify organization/project
→ select primary immutable file
→ capture content hash + Design IR ref + provenance
```

No branch-head/latest resolution exists in NODE-50. The QualityResult stores the exact ArtifactVersion FK and artifact content hash.

## Quality dimensions

Canonical dimensions:

```text
constraint_compliance
composition
visual_hierarchy
alignment_spacing
typography_readability
contrast
brand_consistency
identity_consistency
text_accuracy
logo_integrity
qr_readability
image_defects
resolution_export_readiness
```

Every dimension assessment contains score 0–100, confidence 0–1, threshold, severity, evidence ids and grader identity.

## Evidence priority

Evidence is normalized through `QualitySignalBundle` and classified as:

```text
constraint_runtime
design_ir
ocr
qr_decoder
identity_engine
brand_validator
image_metadata
visual_grader
human_calibration
```

Deterministic/authoritative evidence is evaluated before the visual grader. Current adapters normalize NODE-39, NODE-43 and NODE-44 without copying their business rules.

## Hard gates

Hard gates are not weighted-score inputs that can be averaged away. Any deterministic violation with `blocking=true` or `severity=HARD` forces:

```text
FAIL_HARD
```

The independent visual grader schema intentionally cannot emit `HARD`; it may report INFO/WARNING/ERROR only. This prevents a subjective VLM from becoming the sole authority for QR, identity, brand or explicit constraint rejection.

## Quality profiles

Version 1 built-in profiles:

```text
exploration
production-web
brand-strict
product-strict
print
social-fast
```

A `QualityProfileSnapshot` contains exact weights, per-dimension thresholds, overall pass/warning thresholds, low-confidence threshold, hard dimensions, required dimensions and visual-grader requirement. The snapshot has a canonical semantic hash and is persisted by `(profile_id, version)`.

Examples of profile emphasis:

- `brand-strict`: brand consistency, logo integrity, typography and explicit constraints.
- `product-strict`: product identity and image defects outrank aesthetics.
- `print`: resolution/export readiness and typography are emphasized.
- `social-fast`: hierarchy/composition/text accuracy receive higher weight while hard constraints remain absolute.

## Independent critic isolation

A visual critic must have a registered `GraderCalibrationSnapshot` containing:

- grader id;
- provider/model/model revision;
- human dataset hash;
- threshold revision;
- sample count;
- precision/recall;
- false positive/negative rates;
- inter-rater agreement when available.

The production registry requires the exact calibration to be `is_current=true`.

`ModelGatewayVisualGraderAdapter` uses NODE-22 `llm.vision`, pins the calibrated provider/model, sets `allow_fallback=false`, and verifies the returned provider/model. If the Artifact provenance shows the same generator provider+model as the calibrated critic, evaluation becomes `REVIEW_REQUIRED` rather than self-review.

A model revision change requires a new calibration snapshot before that revision can become the current critic.

## Critic output contract

The VLM produces structured assessments, non-hard violations, strengths and typed repair actions. Free-form prose is not sufficient.

Registered repair actions:

```text
SET_PROPERTY
MOVE_NODE
RESIZE_NODE
REPLACE_TEXT
REPLACE_ASSET
SET_FONT
SET_COLOR
SET_SPACING
REGENERATE_REGION
REGENERATE_ASSET
```

Actions must contain a target and reason code; operations with required payloads such as `SET_PROPERTY` and `REPLACE_TEXT` fail validation when those payloads are absent. NODE-51 may consume these commands, but NODE-50 itself never applies them.

## Gate algorithm

```text
load exact ArtifactVersion
→ run all deterministic signal adapters
→ deterministic hard violation? FAIL_HARD
→ validate current critic calibration
→ invoke independent calibrated VLM
→ merge dimension assessments with deterministic evidence weighted higher
→ missing required dimension? REVIEW_REQUIRED
→ low confidence on high-impact/hard dimension? REVIEW_REQUIRED
→ below quality threshold + typed repair exists? FAIL_REPAIRABLE
→ below threshold without safe registered repair? REVIEW_REQUIRED
→ nonblocking warnings? PASS_WITH_WARNINGS
→ otherwise PASS
```

Visual grader timeout/unavailability/calibration mismatch never converts to PASS. It produces `REVIEW_REQUIRED` when visual grading is required.

## Persistence

Alembic `20260818_0019` follows NODE-49 `20260817_0018` and adds:

```text
quality_profile_snapshots
quality_grader_calibrations
artifact_quality_results
quality_dimension_assessments
quality_violations
```

`artifact_quality_results.artifact_version_id` directly references `artifact_versions(id)` and stores the exact content hash used by evaluation. ArtifactVersion content is not mutated to rewrite history.

The result row stores the full structured QualityResult JSON; normalized dimension/violation tables make quality status queryable for product surfaces, release gates and NODE-51.

## Idempotency

QualityResult id is deterministic from `(organization_id, operation_id)`. Database uniqueness also enforces `(organization_id, operation_id)`.

Reusing an operation id with a different exact ArtifactVersion/profile/calibration is a conflict; repeated delivery of the same evaluation returns the existing result.

## Calibration truth

The committed deterministic benchmark is a **control-plane performance benchmark**, not human calibration evidence. Production `COMPLETE` requires human-labeled benchmark sets and published calibration rows with measured FP/FN and inter-rater agreement.

## Validation gates

Dedicated CI requires:

1. architecture compile/static checks + gap-ledger parse;
2. canonical quality scenarios, adapter tests, codec, Model Gateway isolation, Ruff and Pyright;
3. PostgreSQL migration to Alembic head plus exact ArtifactVersion/calibration/hard-block schema checks;
4. deterministic quality scoring benchmark.

Hosted/live acceptance remains separate from implementation evidence.
